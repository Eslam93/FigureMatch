/**
 * Unit tests for `resolveEndpointContext`. The point of this test file
 * is to lock down the strict validation introduced after PR #144 left
 * `requireContext` with only a non-empty-string check — operators could
 * still pass `lol`, `http://localhost:3000`, or an empty entry and
 * synth would succeed.
 */

import {
  SYNTHETIC_CORS_ORIGINS,
  SYNTHETIC_IMAGES_CDN_BASE_URL,
  resolveEndpointContext,
} from "../lib/endpoint-context";

const validCors = "https://app.example.com";
const validImages = "https://api.example.com/local-images";

describe("resolveEndpointContext — happy path", () => {
  it("accepts a single https origin and a trailing-slash-stripped image base URL", () => {
    const resolved = resolveEndpointContext({
      corsOrigins: `${validCors}/`,
      imagesCdnBaseUrl: `${validImages}/`,
      allowSyntheticEndpoints: false,
    });
    expect(resolved.corsOrigins).toBe(validCors);
    expect(resolved.imagesCdnBaseUrl).toBe(validImages);
    expect(resolved.syntheticEndpointsUsed).toBe(false);
  });

  it("accepts and de-dupes a CSV list", () => {
    const resolved = resolveEndpointContext({
      corsOrigins: `${validCors},${validCors},https://other.example.com`,
      imagesCdnBaseUrl: validImages,
      allowSyntheticEndpoints: false,
    });
    expect(resolved.corsOrigins).toBe(
      `${validCors},https://other.example.com`,
    );
  });

  it("trims whitespace around CSV entries", () => {
    const resolved = resolveEndpointContext({
      corsOrigins: ` ${validCors} ,  https://other.example.com  `,
      imagesCdnBaseUrl: validImages,
      allowSyntheticEndpoints: false,
    });
    expect(resolved.corsOrigins).toBe(
      `${validCors},https://other.example.com`,
    );
  });
});

describe("resolveEndpointContext — missing values", () => {
  it("throws on missing cors_origins without the escape hatch", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: undefined,
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/Missing required context 'cors_origins'/);
  });

  it("throws on missing images_cdn_base_url without the escape hatch", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: validCors,
        imagesCdnBaseUrl: undefined,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/Missing required context 'images_cdn_base_url'/);
  });

  it("throws on empty string for cors_origins", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: "",
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/Missing required context 'cors_origins'/);
  });

  it("falls back to synthetic placeholders when escape hatch is on", () => {
    const resolved = resolveEndpointContext({
      corsOrigins: undefined,
      imagesCdnBaseUrl: undefined,
      allowSyntheticEndpoints: true,
    });
    expect(resolved.corsOrigins).toBe(SYNTHETIC_CORS_ORIGINS);
    expect(resolved.imagesCdnBaseUrl).toBe(SYNTHETIC_IMAGES_CDN_BASE_URL);
    expect(resolved.syntheticEndpointsUsed).toBe(true);
  });
});

describe("resolveEndpointContext — bad-shape values", () => {
  it("rejects a non-URL string", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: "lol",
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/is not a valid URL/);
  });

  it("rejects an http:// origin (must be https)", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: "http://app.example.com",
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/must use https/);
  });

  it("rejects a localhost origin", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: "https://localhost:3000",
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/loopback host/);
  });

  it("rejects a 127.0.0.1 origin", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: "https://127.0.0.1:3000",
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/loopback host/);
  });

  it("rejects an empty CSV entry between commas", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: `${validCors},,https://other.example.com`,
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/is empty/);
  });

  it("rejects a non-URL images_cdn_base_url", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: validCors,
        imagesCdnBaseUrl: "lol",
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/is not a valid URL/);
  });

  it("rejects an http:// images_cdn_base_url", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: validCors,
        imagesCdnBaseUrl: "http://api.example.com/local-images",
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/must use https/);
  });

  it("rejects a localhost images_cdn_base_url", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: validCors,
        imagesCdnBaseUrl: "https://localhost:8000/local-images",
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/loopback host/);
  });

  it("rejects a cors_origins entry with a non-root path", () => {
    // Browser Origin header is origin-only; an allowlist containing
    // `https://app.example.com/foo` would never match the actual
    // `https://app.example.com` the browser sends.
    expect(() =>
      resolveEndpointContext({
        corsOrigins: "https://app.example.com/foo",
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/must be an origin/);
  });

  it("rejects a cors_origins entry with a query string", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: "https://app.example.com?x=1",
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/must be an origin/);
  });

  it("rejects a cors_origins entry with a fragment", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: "https://app.example.com#frag",
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/must be an origin/);
  });

  it("canonicalizes cors origins via url.origin (default port elided, case normalized)", () => {
    const resolved = resolveEndpointContext({
      // Mixed case host + explicit default https port + trailing slash.
      // url.origin returns `https://app.example.com` for all three.
      corsOrigins: "https://APP.example.com:443/",
      imagesCdnBaseUrl: validImages,
      allowSyntheticEndpoints: false,
    });
    expect(resolved.corsOrigins).toBe("https://app.example.com");
  });
});

describe("resolveEndpointContext — .invalid TLD policy", () => {
  it("rejects a .invalid cors origin without the escape hatch", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: "https://something.invalid",
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/'.invalid' TLD/);
  });

  it("rejects a .invalid images_cdn_base_url without the escape hatch", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: validCors,
        imagesCdnBaseUrl: "https://something.invalid/local-images",
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/'.invalid' TLD/);
  });

  it("accepts operator-supplied .invalid values when the escape hatch is on and flags them as synthetic", () => {
    const resolved = resolveEndpointContext({
      corsOrigins: "https://bootstrap.invalid",
      imagesCdnBaseUrl: "https://bootstrap.invalid/local-images",
      allowSyntheticEndpoints: true,
    });
    expect(resolved.corsOrigins).toBe("https://bootstrap.invalid");
    expect(resolved.imagesCdnBaseUrl).toBe(
      "https://bootstrap.invalid/local-images",
    );
    // Operator-supplied `.invalid` values produce the same broken
    // deploy as resolver-filled placeholders — the deployed app will
    // reject every request — so the CDK warning + stack tag MUST fire.
    expect(resolved.syntheticEndpointsUsed).toBe(true);
  });

  it("sets syntheticEndpointsUsed when the resolver itself filled in placeholders", () => {
    const resolved = resolveEndpointContext({
      corsOrigins: undefined,
      imagesCdnBaseUrl: validImages,
      allowSyntheticEndpoints: true,
    });
    expect(resolved.corsOrigins).toBe(SYNTHETIC_CORS_ORIGINS);
    expect(resolved.syntheticEndpointsUsed).toBe(true);
  });

  it("flags syntheticEndpointsUsed when any CSV entry uses .invalid", () => {
    const resolved = resolveEndpointContext({
      // Mixed list: one real origin + one placeholder. The deploy is
      // still going to break for the placeholder users, so the flag
      // must fire on a mixed list too.
      corsOrigins: `${validCors},https://bootstrap.invalid`,
      imagesCdnBaseUrl: validImages,
      allowSyntheticEndpoints: true,
    });
    expect(resolved.syntheticEndpointsUsed).toBe(true);
  });

  it("does NOT set syntheticEndpointsUsed when escape hatch is on but both values are real", () => {
    // The flag is about "the resolved values are synthetic," not "the
    // operator passed the escape-hatch flag." A deploy with real
    // values + the escape hatch flipped on shouldn't trigger a
    // bootstrap-mode warning.
    const resolved = resolveEndpointContext({
      corsOrigins: validCors,
      imagesCdnBaseUrl: validImages,
      allowSyntheticEndpoints: true,
    });
    expect(resolved.syntheticEndpointsUsed).toBe(false);
  });
});

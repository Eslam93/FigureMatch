/**
 * Pure CDK-context resolver for the two endpoint values App Runner has
 * to know at synth time: `cors_origins` (allowed browser origins) and
 * `images_cdn_base_url` (public URL prefix for generated image bytes).
 *
 * Lives in its own module so the validation logic can be unit-tested
 * without instantiating the CDK App. `bin/figurematch.ts` is a thin
 * adapter that pulls strings out of `app.node.tryGetContext(...)` and
 * hands them here.
 *
 * # Why the validation is strict
 *
 * Round 1 of the deploy-hardening pass guarded `requireContext` only
 * against missing values, which left a path where `-c cors_origins=lol`
 * or `-c images_cdn_base_url=http://localhost:3000` would synth fine
 * and break at first request. The fix is to validate the shape too:
 * https only, no localhost/loopback, no `.invalid` (the IANA-reserved
 * suffix we use for the synthetic placeholder). Operators who genuinely
 * need to bootstrap before real values exist must opt in with
 * `-c allow_synthetic_endpoints=true`, which keeps the failure mode
 * loud (a CDK warning + a stack tag) rather than silent.
 *
 * # Strict, not env-aware
 *
 * Local development uses the backend's `.env`/`Settings` directly and
 * never goes through `cdk deploy`, so there's no legitimate
 * localhost-in-CDK-context case. Keeping the rule strict avoids a
 * carve-out that would just be a future footgun.
 */

export interface EndpointContextInput {
  /** Raw `-c cors_origins=...` value; CSV string or undefined. */
  corsOrigins: string | undefined;
  /** Raw `-c images_cdn_base_url=...` value or undefined. */
  imagesCdnBaseUrl: string | undefined;
  /** True if `-c allow_synthetic_endpoints=true` is set. */
  allowSyntheticEndpoints: boolean;
}

export interface ResolvedEndpoints {
  /** CSV string of validated, normalized origins ready for App Runner. */
  corsOrigins: string;
  /** Normalized https URL ready for App Runner; no trailing slash. */
  imagesCdnBaseUrl: string;
  /** True iff either value was filled from the synthetic placeholder. */
  syntheticEndpointsUsed: boolean;
}

/** Placeholder origin used when the operator opts into synthetic mode. */
export const SYNTHETIC_CORS_ORIGINS = "https://figurematch-bootstrap.invalid";

/** Placeholder image base URL used when the operator opts into synthetic mode. */
export const SYNTHETIC_IMAGES_CDN_BASE_URL =
  "https://figurematch-bootstrap.invalid/local-images";

const LOOPBACK_HOSTS = new Set([
  "localhost",
  "127.0.0.1",
  "0.0.0.0",
  "[::1]",
  "::1",
]);

function isLoopbackHost(hostname: string): boolean {
  return LOOPBACK_HOSTS.has(hostname.toLowerCase());
}

function isInvalidTld(hostname: string): boolean {
  return hostname.toLowerCase().endsWith(".invalid");
}

function parseHttpsUrl(raw: string, fieldName: string): URL {
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error(
      `[CDK] ${fieldName} value '${raw}' is not a valid URL. ` +
        `Pass a fully-qualified https URL (e.g. https://app.example.com).`,
    );
  }
  if (parsed.protocol !== "https:") {
    throw new Error(
      `[CDK] ${fieldName} value '${raw}' must use https. ` +
        `App Runner is reached over TLS and the refresh cookie is ` +
        `SameSite=None which browsers only honor on https origins.`,
    );
  }
  return parsed;
}

function validateOrigin(
  raw: string,
  index: number,
  allowSynthetic: boolean,
): string {
  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    throw new Error(
      `[CDK] cors_origins entry #${index + 1} is empty. ` +
        `Remove the stray comma or supply a fully-qualified https origin.`,
    );
  }
  const url = parseHttpsUrl(trimmed, `cors_origins entry #${index + 1}`);
  if (isLoopbackHost(url.hostname)) {
    throw new Error(
      `[CDK] cors_origins entry #${index + 1} ('${trimmed}') points at a ` +
        `loopback host. The deployed backend cannot serve a browser on ` +
        `localhost. Use the real Amplify URL.`,
    );
  }
  if (isInvalidTld(url.hostname) && !allowSynthetic) {
    throw new Error(
      `[CDK] cors_origins entry #${index + 1} ('${trimmed}') uses the ` +
        `'.invalid' TLD reserved for placeholders. Pass a real origin, ` +
        `or set '-c allow_synthetic_endpoints=true' to bootstrap.`,
    );
  }
  // CORS Origin headers from browsers are origin-only: scheme + host +
  // optional non-default port, with no path/query/fragment. If the
  // operator passes `https://app.example.com/foo`, the backend's
  // allowlist will contain that value but the browser will send
  // `https://app.example.com` and the CORS check will fail at runtime
  // even though synth succeeded. Catch that here.
  if (url.pathname !== "/" || url.search !== "" || url.hash !== "") {
    throw new Error(
      `[CDK] cors_origins entry #${index + 1} ('${trimmed}') must be an ` +
        `origin (scheme + host + optional port), not a URL with path, ` +
        `query, or fragment. The browser's Origin header is origin-only, ` +
        `so the allowlist would never match.`,
    );
  }
  // Return `url.origin` rather than the trimmed input: it canonicalizes
  // host case, elides default ports (`:443` → `""`), and strips any
  // trailing slash. This is the exact byte sequence a compliant browser
  // will send in the `Origin` header.
  return url.origin;
}

function resolveCorsOrigins(input: EndpointContextInput): string {
  const supplied = input.corsOrigins;
  if (supplied === undefined || supplied.length === 0) {
    if (input.allowSyntheticEndpoints) {
      return SYNTHETIC_CORS_ORIGINS;
    }
    throw new Error(
      `[CDK] Missing required context 'cors_origins'. ` +
        `Pass '-c cors_origins=https://your-amplify-domain.example.com' on ` +
        `cdk synth/deploy, or set '-c allow_synthetic_endpoints=true' to ` +
        `bootstrap with a clearly-synthetic placeholder.`,
    );
  }
  const entries = supplied
    .split(",")
    .map((s, i) => validateOrigin(s, i, input.allowSyntheticEndpoints));
  // De-dup while preserving order.
  const seen = new Set<string>();
  const unique: string[] = [];
  for (const entry of entries) {
    if (!seen.has(entry)) {
      seen.add(entry);
      unique.push(entry);
    }
  }
  return unique.join(",");
}

function resolveImagesCdnBaseUrl(input: EndpointContextInput): string {
  const supplied = input.imagesCdnBaseUrl;
  if (supplied === undefined || supplied.length === 0) {
    if (input.allowSyntheticEndpoints) {
      return SYNTHETIC_IMAGES_CDN_BASE_URL;
    }
    throw new Error(
      `[CDK] Missing required context 'images_cdn_base_url'. ` +
        `Pass '-c images_cdn_base_url=https://api.example.com/local-images' ` +
        `on cdk synth/deploy, or set '-c allow_synthetic_endpoints=true' ` +
        `to bootstrap with a clearly-synthetic placeholder.`,
    );
  }
  const trimmed = supplied.trim();
  const url = parseHttpsUrl(trimmed, "images_cdn_base_url");
  if (isLoopbackHost(url.hostname)) {
    throw new Error(
      `[CDK] images_cdn_base_url '${trimmed}' points at a loopback host. ` +
        `The deployed frontend cannot fetch images from localhost.`,
    );
  }
  if (isInvalidTld(url.hostname) && !input.allowSyntheticEndpoints) {
    throw new Error(
      `[CDK] images_cdn_base_url '${trimmed}' uses the '.invalid' TLD ` +
        `reserved for placeholders. Pass a real URL, or set ` +
        `'-c allow_synthetic_endpoints=true' to bootstrap.`,
    );
  }
  return trimmed.replace(/\/+$/, "");
}

function corsHasInvalidHostname(corsOrigins: string): boolean {
  return corsOrigins.split(",").some((entry) => {
    try {
      return isInvalidTld(new URL(entry).hostname);
    } catch {
      return false;
    }
  });
}

function imagesHasInvalidHostname(url: string): boolean {
  try {
    return isInvalidTld(new URL(url).hostname);
  } catch {
    return false;
  }
}

export function resolveEndpointContext(
  input: EndpointContextInput,
): ResolvedEndpoints {
  const corsOrigins = resolveCorsOrigins(input);
  const imagesCdnBaseUrl = resolveImagesCdnBaseUrl(input);
  // Flag the synthetic state whenever either resolved value is a
  // placeholder — whether the resolver filled it in itself OR the
  // operator passed their own `.invalid` value through the escape
  // hatch. Both cases produce a deploy that fails on the first real
  // request, so the warning and CloudFormation tag in `bin/figurematch.ts`
  // should fire either way.
  const syntheticEndpointsUsed =
    corsOrigins === SYNTHETIC_CORS_ORIGINS ||
    imagesCdnBaseUrl === SYNTHETIC_IMAGES_CDN_BASE_URL ||
    corsHasInvalidHostname(corsOrigins) ||
    imagesHasInvalidHostname(imagesCdnBaseUrl);
  return { corsOrigins, imagesCdnBaseUrl, syntheticEndpointsUsed };
}

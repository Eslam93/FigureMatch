// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

/**
 * `loadConfig` smoke tests.
 *
 * These tests exist mostly to keep `jest` honest while the stacks
 * haven't landed yet — once PR 2 adds `NetworkStack`, every subsequent
 * PR adds a snapshot test next to its stack file.
 */

import { loadConfig } from "../lib/config";

describe("loadConfig", () => {
  it("returns a populated config for env=dev", () => {
    const cfg = loadConfig("dev");
    expect(cfg.envName).toBe("dev");
    expect(cfg.region).toBe("us-east-1");
    expect(cfg.rdsInstanceClass).toBe("db.t4g.micro");
    expect(cfg.apprunnerMinInstances).toBe(1);
    expect(cfg.apprunnerMaxInstances).toBe(3);
    expect(cfg.logRetentionDays).toBe(14);
  });

  it("throws on an unknown env name", () => {
    expect(() => loadConfig("prdo")).toThrow(/Unknown environment/);
  });

  it("throws on a documented-but-unimplemented env", () => {
    expect(() => loadConfig("staging")).toThrow(/not implemented yet/);
    expect(() => loadConfig("prod")).toThrow(/not implemented yet/);
  });
});

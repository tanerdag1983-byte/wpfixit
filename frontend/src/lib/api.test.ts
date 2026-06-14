import { describe, expect, it } from "vitest";

import { resolveAccessToken } from "./api";

describe("resolveAccessToken", () => {
  it("uses a local development token when no Supabase session exists", () => {
    expect(resolveAccessToken(undefined, "demo-token")).toBe("demo-token");
  });

  it("prefers the authenticated Supabase session", () => {
    expect(resolveAccessToken("session-token", "demo-token")).toBe(
      "session-token",
    );
  });
});

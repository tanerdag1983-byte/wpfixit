import { describe, expect, it } from "vitest";

import { resolveApiBaseUrl } from "./api";

describe("resolveApiBaseUrl", () => {
  it("prefers the configured API base URL when present", () => {
    expect(
      resolveApiBaseUrl("https://custom-api.example.com", "localhost"),
    ).toBe("https://custom-api.example.com");
  });

  it("keeps localhost for local development without an explicit env var", () => {
    expect(resolveApiBaseUrl(undefined, "localhost")).toBe(
      "http://localhost:8000",
    );
    expect(resolveApiBaseUrl(undefined, "127.0.0.1")).toBe(
      "http://localhost:8000",
    );
  });

  it("falls back to the Render API for previews when the env var is missing", () => {
    expect(
      resolveApiBaseUrl(
        undefined,
        "wpfixit-git-feature-platform-build-tanerdag1983-9949s-projects.vercel.app",
      ),
    ).toBe("https://wp-fixpilot-api.onrender.com");
  });
});

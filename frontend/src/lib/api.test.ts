import { afterEach, describe, expect, it, vi } from "vitest";

import { apiRequest, resolveAccessToken } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("resolveAccessToken", () => {
  it("uses a local development token when no Supabase session exists", () => {
    expect(resolveAccessToken(undefined, "demo-token")).toBe("demo-token");
  });

  it("prefers the authenticated Supabase session", () => {
    expect(resolveAccessToken("session-token", "demo-token")).toBe(
      "session-token",
    );
  });

  it("formats FastAPI validation details instead of showing object text", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail: [
            {
              loc: ["body", "company_name"],
              msg: "Field required",
              type: "missing",
            },
          ],
        }),
        {
          status: 422,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await expect(apiRequest("/projects/project-1/company-profile")).rejects.toThrow(
      "company_name: Field required",
    );
  });
});

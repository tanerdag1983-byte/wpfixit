import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GoogleOAuthCallback } from "./GoogleOAuthCallback";

const apiRequest = vi.fn();

vi.mock("../../lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

describe("GoogleOAuthCallback", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    sessionStorage.clear();
    window.history.replaceState(null, "", "/auth/google/callback?code=abc&state=xyz");
    apiRequest.mockResolvedValue({
      google_connection_id: "google-1",
      project_id: "shm",
    });
  });

  it("exchanges the Google callback and stores the connection for property binding", async () => {
    render(<GoogleOAuthCallback />);

    expect(await screen.findByText("Google-koppeling afronden...")).toBeVisible();
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/auth/google/callback",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ code: "abc", state: "xyz" }),
        }),
      ),
    );
    expect(sessionStorage.getItem("wpfixpilot.googleConnectionId")).toBe(
      "google-1",
    );
  });
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ActionWorkspace } from "./ActionWorkspace";

const apiRequest = vi.fn();

vi.mock("../../../lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

describe("ActionWorkspace", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({
      items: [
        {
          id: "recommendation-1",
          url: "https://shmtransmissie.nl/revisie",
          priority: "high",
          recommendation: "Herschrijf de SEO-title.",
          provider: "rules",
          model: null,
          approval_state: "proposed",
        },
      ],
    });
  });

  it("generates project recommendations through the API", async () => {
    render(<ActionWorkspace projectId="shm" />);

    fireEvent.click(
      screen.getByRole("button", { name: "Aanbevelingen genereren" }),
    );

    expect(await screen.findByText("Herschrijf de SEO-title.")).toBeVisible();
    expect(screen.getByText("Regels-engine")).toBeVisible();
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/shm/recommendations/generate?limit=10",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });
});

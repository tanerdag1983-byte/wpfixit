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
          wordpress_page_id: "wp-page-1",
          url: "https://shmtransmissie.nl/revisie",
          action_type: "seo_title",
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

  it("creates a change proposal from a recommendation", async () => {
    render(<ActionWorkspace projectId="shm" />);

    fireEvent.click(
      screen.getByRole("button", { name: "Aanbevelingen genereren" }),
    );
    fireEvent.click(await screen.findByText("Herschrijf de SEO-title."));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/shm/change-proposals",
        {
          method: "POST",
          body: JSON.stringify({
            wordpress_page_id: "wp-page-1",
            recommendation_id: "recommendation-1",
            change_type: "seo_title",
            before_value: "",
            after_value: "Herschrijf de SEO-title.",
          }),
        },
      ),
    );
  });
});

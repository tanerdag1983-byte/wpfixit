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
  });

  it("loads saved recommendations after a refresh", async () => {
    apiRequest.mockResolvedValueOnce({ items: [recommendation] });

    render(<ActionWorkspace projectId="shm" />);

    expect(await screen.findByText("Maak de SEO-title specifieker")).toBeVisible();
    expect(apiRequest).toHaveBeenCalledWith(
      "/projects/shm/recommendations?limit=10",
    );
  });

  it("generates project recommendations through the API", async () => {
    apiRequest
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce({ items: [recommendation] });

    render(<ActionWorkspace projectId="shm" />);

    fireEvent.click(
      screen.getByRole("button", { name: "Aanbevelingen genereren" }),
    );

    expect(await screen.findByText("Maak de SEO-title specifieker")).toBeVisible();
    expect(screen.getByText("Regels-engine")).toBeVisible();
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/shm/recommendations/generate?limit=10",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("creates a change proposal from a recommendation", async () => {
    apiRequest.mockResolvedValueOnce({ items: [recommendation] }).mockResolvedValueOnce({});

    render(<ActionWorkspace projectId="shm" />);

    fireEvent.click(await screen.findByText("Maak de SEO-title specifieker"));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/shm/recommendations/recommendation-1/change-proposal",
        { method: "POST" },
      ),
    );
  });

  it("shows a short action title instead of full publishable HTML", async () => {
    apiRequest.mockResolvedValueOnce({
      items: [
        {
          ...recommendation,
          action_type: "content",
          recommendation:
            "<h2>Waarom deze pagina belangrijk is</h2><p>Bedankpagina offerte helpt bezoekers snel te begrijpen welke oplossing past bij hun situatie.</p>",
        },
      ],
    });

    render(<ActionWorkspace projectId="shm" />);

    expect(await screen.findByText("Verbeter de pagina-inhoud")).toBeVisible();
    expect(
      screen.queryByText(/Waarom deze pagina belangrijk is/),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/<h2>/)).not.toBeInTheDocument();
  });
});

const recommendation = {
  id: "recommendation-1",
  wordpress_page_id: "wp-page-1",
  url: "https://shmtransmissie.nl/revisie",
  action_type: "seo_title",
  priority: "high",
  recommendation: "Herschrijf de SEO-title.",
  provider: "rules",
  model: null,
  approval_state: "proposed",
};

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OpportunitiesPage } from "./OpportunitiesPage";

const apiRequest = vi.fn();

vi.mock("../../lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

describe("OpportunitiesPage", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/keyword-opportunities")) {
        return Promise.resolve({
          items: [
            {
              id: "keyword-1",
              keyword: "automatische transmissie revisie",
              search_volume: 320,
              cpc: 4.25,
              competition_level: "medium",
              keyword_difficulty: 38,
              intent: "commercial",
              target_url: null,
              target_classification: "new_page",
              target_score: 0,
              target_evidence: ["no_distinctive_page_match"],
              recommended_action:
                "Maak een nieuwe landingspagina voor dit zoekwoord.",
              source: "dataforseo",
            },
          ],
        });
      }
      return Promise.resolve({ synced: 1 });
    });
  });

  it("shows live keyword opportunities", async () => {
    render(<OpportunitiesPage projectId="project-1" />);

    expect(screen.getByRole("heading", { name: "Kansen" })).toBeVisible();
    expect(
      await screen.findByText("automatische transmissie revisie"),
    ).toBeVisible();
    expect(screen.getByText(/320 zoekopdrachten/)).toBeVisible();
    expect(screen.getByText("DataForSEO")).toBeVisible();
    expect(screen.getByText("Nieuwe pagina aanbevolen")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Pagina laten maken" }),
    ).toBeVisible();
  });

  it("syncs and reloads keyword opportunities", async () => {
    render(<OpportunitiesPage projectId="project-1" />);
    await screen.findByText("automatische transmissie revisie");

    fireEvent.click(screen.getByRole("button", { name: "Nieuwe kansen ophalen" }));

    expect(
      await screen.findByText("1 zoekwoordkans bijgewerkt."),
    ).toBeVisible();
    expect(apiRequest).toHaveBeenCalledWith(
      "/projects/project-1/sync-keyword-opportunities",
      { method: "POST" },
    );
  });
});

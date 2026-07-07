import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
      if (path.endsWith("/page-blueprints")) {
        return Promise.resolve({
          items: [
            { id: "blueprint-1", name: "Dienstpagina", page_type: "service", version: 2, state: "ready", is_default_for_page_type: true },
            { id: "blueprint-2", name: "Merkpagina", page_type: "brand", version: 1, state: "ready", is_default_for_page_type: true },
          ],
        });
      }
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
    ).toBeDisabled();
    expect(screen.getByLabelText("Paginatype voor automatische transmissie revisie")).toBeVisible();
  });

  it("marks generated new-page opportunities and reopens the saved proposal", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/page-blueprints")) {
        return Promise.resolve({
          items: [
            { id: "blueprint-1", name: "Dienstpagina", page_type: "service", version: 2, state: "ready", is_default_for_page_type: true },
          ],
        });
      }
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
              proposal_summary: {
                state: "proposed",
                current_version_id: "proposal-2",
              },
            },
          ],
        });
      }
      return Promise.resolve({ synced: 1 });
    });
    render(<OpportunitiesPage projectId="project-1" />);

    expect(await screen.findByText("Gegenereerd")).toBeVisible();
    expect(screen.getByRole("button", { name: "Voorstel bekijken" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Opnieuw genereren" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Voorstel bekijken" }));
    expect(window.sessionStorage.getItem("page-proposal-id:project-1")).toBe("proposal-2");
    expect(window.location.hash).toBe("#page-proposal");
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

  it("shows page proposal errors next to the selected opportunity", async () => {
    let proposalAttempt = 0;
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/page-blueprints")) {
        return Promise.resolve({
          items: [
            { id: "blueprint-1", name: "Dienstpagina", page_type: "service", version: 2, state: "ready", is_default_for_page_type: true },
          ],
        });
      }
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
              recommended_action: "Maak een nieuwe landingspagina.",
              source: "dataforseo",
            },
            {
              id: "keyword-2",
              keyword: "7g dct automatische transmissie",
              search_volume: 10,
              cpc: null,
              competition_level: null,
              keyword_difficulty: null,
              intent: "informational",
              target_url: null,
              target_classification: "new_page",
              target_score: 0,
              target_evidence: ["no_distinctive_page_match"],
              recommended_action: "Maak een tweede landingspagina.",
              source: "dataforseo",
            },
          ],
        });
      }
      if (path.endsWith("/sync-keyword-opportunities")) {
        return Promise.resolve({ synced: 2 });
      }
      proposalAttempt += 1;
      return proposalAttempt === 1
        ? Promise.reject(new Error("Project AI model is not configured"))
        : new Promise(() => undefined);
    });
    render(<OpportunitiesPage projectId="project-1" />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Nieuwe kansen ophalen" }),
    );
    expect(await screen.findByText("2 zoekwoordkansen bijgewerkt.")).toBeVisible();

    const selectedCard = screen
      .getByText("7g dct automatische transmissie")
      .closest("article");
    const otherCard = screen
      .getByText("automatische transmissie revisie")
      .closest("article");
    expect(selectedCard).not.toBeNull();
    expect(otherCard).not.toBeNull();
    fireEvent.change(
      within(selectedCard!).getByLabelText(
        "Paginatype voor 7g dct automatische transmissie",
      ),
      { target: { value: "service" } },
    );
    fireEvent.click(
      within(selectedCard!).getByRole("button", { name: "Pagina laten maken" }),
    );

    expect(await within(selectedCard!).findByRole("alert")).toHaveTextContent(
      "Project AI model is not configured",
    );
    expect(within(otherCard!).queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("2 zoekwoordkansen bijgewerkt.")).toBeVisible();

    fireEvent.click(
      within(selectedCard!).getByRole("button", { name: "Pagina laten maken" }),
    );
    await waitFor(() =>
      expect(within(selectedCard!).queryByRole("alert")).not.toBeInTheDocument(),
    );
  });

  it("requires and submits an explicit blueprint page type", async () => {
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.endsWith("/page-blueprints")) {
        return Promise.resolve({
          items: [
            { id: "blueprint-2", name: "Merkpagina", page_type: "brand", version: 1, state: "ready", is_default_for_page_type: true },
          ],
        });
      }
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
              target_evidence: [],
              recommended_action: "Maak een landingspagina.",
              source: "dataforseo",
            },
          ],
        });
      }
      if (init?.method === "POST") return Promise.resolve({ id: "proposal-1" });
      return Promise.resolve({ synced: 1 });
    });
    render(<OpportunitiesPage projectId="project-1" />);
    const button = await screen.findByRole("button", { name: "Pagina laten maken" });
    fireEvent.change(
      screen.getByLabelText("Paginatype voor automatische transmissie revisie"),
      { target: { value: "brand" } },
    );
    fireEvent.click(button);

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/project-1/keyword-opportunities/keyword-1/page-proposal",
        { method: "POST", body: JSON.stringify({ page_type: "brand" }) },
      ),
    );
  });

  it("links to blueprint settings when no ready default exists", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/page-blueprints")) return Promise.resolve({ items: [] });
      if (path.endsWith("/keyword-opportunities")) {
        return Promise.resolve({ items: [{
          id: "keyword-1", keyword: "dsg revisie", search_volume: 10, cpc: null,
          competition_level: null, keyword_difficulty: null, intent: "commercial",
          target_url: null, target_classification: "new_page", target_score: 0,
          target_evidence: [], recommended_action: "Maak een pagina.", source: "dataforseo",
        }] });
      }
      return Promise.resolve({ synced: 0 });
    });
    render(<OpportunitiesPage projectId="project-1" />);

    expect(await screen.findByRole("link", { name: "Standaardblueprint instellen" })).toHaveAttribute("href", "#settings");
    expect(screen.getByRole("button", { name: "Pagina laten maken" })).toBeDisabled();
  });
});

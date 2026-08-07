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

  it("creates an improvement proposal for an existing page", async () => {
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.endsWith("/page-blueprints")) return Promise.resolve({ items: [] });
      if (path.endsWith("/keyword-opportunities")) {
        return Promise.resolve({
          items: [{
            id: "existing-1",
            keyword: "dsg revisie",
            search_volume: 320,
            cpc: 4.25,
            competition_level: "medium",
            keyword_difficulty: 38,
            intent: "commercial",
            target_url: "https://example.com/dsg-revisie",
            target_classification: "existing_page",
            target_score: 91,
            target_evidence: ["strong_existing_page_match"],
            recommended_action: "Verbeter de bestaande pagina.",
            source: "dataforseo",
          }],
        });
      }
      if (init?.method === "POST") return Promise.resolve({ id: "proposal-existing" });
      return Promise.resolve({});
    });
    render(<OpportunitiesPage projectId="project-1" />);

    fireEvent.change(await screen.findByLabelText("Paginatype voor dsg revisie"), {
      target: { value: "service" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Verbeteringsvoorstel maken" }),
    );

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/projects/project-1/keyword-opportunities/existing-1/page-proposal",
      { method: "POST", body: JSON.stringify({ page_type: "service" }) },
    ));
    expect(window.sessionStorage.getItem("page-proposal-id:project-1")).toBe(
      "proposal-existing",
    );
  });

  it("keeps an existing-page opportunity open while WordPress captures its snapshot", async () => {
    window.sessionStorage.removeItem("page-proposal-id:project-1");
    window.location.hash = "";
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.endsWith("/page-blueprints")) return Promise.resolve({ items: [] });
      if (path.endsWith("/keyword-opportunities")) {
        return Promise.resolve({
          items: [{
            id: "existing-waiting",
            keyword: "automaat revisie",
            search_volume: 110,
            target_url: "https://example.com/automaat-revisie",
            target_classification: "existing_page",
            target_score: 88,
            target_evidence: ["strong_existing_page_match"],
            recommended_action: "Verbeter de bestaande pagina.",
            source: "dataforseo",
          }],
        });
      }
      if (init?.method === "POST") {
        return Promise.resolve({
          stage: "waiting_for_wordpress_snapshot",
          snapshot_job_id: "snapshot-job-1",
          source_wordpress_page_id: "wordpress-page-1",
        });
      }
      return Promise.resolve({});
    });
    render(<OpportunitiesPage projectId="project-1" />);

    fireEvent.change(await screen.findByLabelText("Paginatype voor automaat revisie"), {
      target: { value: "service" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verbeteringsvoorstel maken" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "WordPress maakt eerst een veilige momentopname",
    );
    expect(window.sessionStorage.getItem("page-proposal-id:project-1")).toBeNull();
    expect(window.location.hash).not.toBe("#page-proposal");
    expect(screen.getByRole("button", { name: "Verbeteringsvoorstel maken" })).toBeEnabled();
  });

  it("regenerates a saved proposal using its existing page type", async () => {
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
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
                state: "failed",
                current_version_id: "proposal-2",
              },
            },
          ],
        });
      }
      if (path.endsWith("/page-proposals/proposal-2")) {
        return Promise.resolve({
          blueprint: { page_type: "service" },
        });
      }
      if (path.endsWith("/page-proposal") && init?.method === "POST") {
        return Promise.resolve({ id: "proposal-3" });
      }
      return Promise.resolve({ synced: 1 });
    });

    render(<OpportunitiesPage projectId="project-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "Opnieuw genereren" }));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/project-1/page-proposals/proposal-2",
      ),
    );
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/project-1/keyword-opportunities/keyword-1/page-proposal",
        { method: "POST", body: JSON.stringify({ page_type: "service" }) },
      ),
    );
    expect(window.sessionStorage.getItem("page-proposal-id:project-1")).toBe("proposal-3");
    expect(window.location.hash).toBe("#page-proposal");
  });

  it("keeps old rows and reports the new sync counts", async () => {
    let opportunityLoads = 0;
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/page-blueprints")) {
        return Promise.resolve({ items: [] });
      }
      if (path.endsWith("/keyword-opportunities")) {
        opportunityLoads += 1;
        return Promise.resolve({
          items: [
            ...(opportunityLoads === 1
              ? []
              : [{
                  id: "new-keyword",
                  keyword: "nieuwe transmissiekans",
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
                  is_new: true,
                  first_seen_at: "2026-07-30T10:00:00+00:00",
                  last_seen_at: "2026-07-30T10:00:00+00:00",
                }]),
            {
              id: "old-keyword",
              keyword: "bestaande transmissiekans",
              search_volume: 120,
              cpc: null,
              competition_level: null,
              keyword_difficulty: null,
              intent: "informational",
              target_url: null,
              target_classification: "new_page",
              target_score: 0,
              target_evidence: [],
              recommended_action: "Verbeter de bestaande pagina.",
              source: "dataforseo",
              is_new: false,
              first_seen_at: "2026-07-29T10:00:00+00:00",
              last_seen_at: "2026-07-30T10:00:00+00:00",
            },
          ],
        });
      }
      return Promise.resolve({
        run_id: "run-2",
        offset: 50,
        next_offset: 100,
        exhausted: false,
        provider_count: 50,
        accepted_count: 45,
        new_count: 14,
        updated_count: 31,
        rejected_count: 5,
      });
    });
    render(<OpportunitiesPage projectId="project-1" />);
    await screen.findByText("bestaande transmissiekans");

    fireEvent.click(screen.getByRole("button", { name: "Nieuwe kansen ophalen" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "14 nieuw, 31 bijgewerkt, 5 niet relevant",
    );
    expect(screen.getByText("Nieuw")).toBeVisible();
    expect(screen.getByText("bestaande transmissiekans")).toBeVisible();
    expect(apiRequest).toHaveBeenCalledWith(
      "/projects/project-1/sync-keyword-opportunities",
      { method: "POST" },
    );
  });

  it("keeps completed sync counts when the opportunity refresh fails", async () => {
    let opportunityLoads = 0;
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/page-blueprints")) return Promise.resolve({ items: [] });
      if (path.endsWith("/keyword-opportunities")) {
        opportunityLoads += 1;
        return opportunityLoads === 1
          ? Promise.resolve({ items: [] })
          : Promise.reject(new Error("Kansen vernieuwen mislukt"));
      }
      return Promise.resolve({
        run_id: "run-3",
        offset: 100,
        next_offset: 150,
        exhausted: false,
        provider_count: 50,
        accepted_count: 45,
        new_count: 14,
        updated_count: 31,
        rejected_count: 5,
      });
    });
    render(<OpportunitiesPage projectId="project-1" />);
    await screen.findByText(/Nog geen live zoekwoordkansen/);

    fireEvent.click(screen.getByRole("button", { name: "Nieuwe kansen ophalen" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "14 nieuw, 31 bijgewerkt, 5 niet relevant",
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Kansen vernieuwen mislukt",
    );
  });

  it("announces initial loading and load errors", async () => {
    let rejectOpportunities!: (reason: Error) => void;
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/page-blueprints")) return Promise.resolve({ items: [] });
      if (path.endsWith("/keyword-opportunities")) {
        return new Promise((_, reject: (reason: Error) => void) => {
          rejectOpportunities = reject;
        });
      }
      return Promise.resolve({});
    });
    render(<OpportunitiesPage projectId="project-1" />);

    expect(screen.getByRole("status")).toHaveTextContent(
      "Zoekwoordkansen laden...",
    );
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/project-1/keyword-opportunities",
      ),
    );
    rejectOpportunities(new Error("Zoekwoordkansen laden mislukt"));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Zoekwoordkansen laden mislukt",
    );
  });

  it("announces sync errors as alerts", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/page-blueprints")) return Promise.resolve({ items: [] });
      if (path.endsWith("/keyword-opportunities")) return Promise.resolve({ items: [] });
      return Promise.reject(new Error("DataForSEO tijdelijk niet beschikbaar"));
    });
    render(<OpportunitiesPage projectId="project-1" />);
    await screen.findByText(/Nog geen live zoekwoordkansen/);

    fireEvent.click(screen.getByRole("button", { name: "Nieuwe kansen ophalen" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "DataForSEO tijdelijk niet beschikbaar",
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
        return Promise.resolve({
          run_id: "run-2",
          offset: 50,
          next_offset: 100,
          exhausted: false,
          provider_count: 2,
          accepted_count: 2,
          new_count: 0,
          updated_count: 2,
          rejected_count: 0,
        });
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
    expect(await screen.findByText("0 nieuw, 2 bijgewerkt, 0 niet relevant")).toBeVisible();

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
    expect(screen.getByText("0 nieuw, 2 bijgewerkt, 0 niet relevant")).toBeVisible();

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

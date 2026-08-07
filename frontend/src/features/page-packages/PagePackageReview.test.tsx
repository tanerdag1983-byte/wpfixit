import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PagePackageReview } from "./PagePackageReview";

const apiRequest = vi.fn();
const openWindow = vi.fn();

vi.mock("../../lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

const proposal = {
  id: "proposal-1",
  state: "proposed",
  provider: "openrouter",
  model: "model-1",
  package: {
    title: "DSG versnellingsbak reviseren",
    slug: "dsg-versnellingsbak-reviseren",
    seo_title: "DSG versnellingsbak reviseren | Specialist",
    meta_description:
      "Laat uw DSG versnellingsbak deskundig onderzoeken en reviseren door een ervaren transmissiespecialist.",
    focus_keyword: "dsg versnellingsbak reviseren",
    replacements: [
      { field_id: "acf-title", value: "DSG revisie Schiedam" },
      { field_id: "acf-copy", value: "<p>Heldere diagnose en revisie.</p>" },
      { field_id: "acf-cta-url", value: "/contact/" },
    ],
    internal_links: [
      { anchor: "contact", url: "https://example.com/contact/" },
    ],
  },
  blueprint: {
    id: "blueprint-service-v2",
    name: "Dienstpagina",
    page_type: "service",
    version: 2,
    structure_hash: "hash-v2",
    builder: "acf",
    seo_plugin: "yoast",
    wordpress_blueprint_id: 902,
    source_wordpress_page_id: "template-page",
  },
  config_snapshot: {
    content_schema: {
      schema_version: "blueprint-v1",
      blocks: [
        {
          id: "hero",
          layout: "hero_algemeen",
          label: "Hero (algemeen)",
          semantic_role: "hero",
          fields: [
            { id: "acf-title", path: "page_blocks/0/title", label: "Titel", value_type: "heading", current_value: "Oude titel", required: true, max_length: 180 },
            { id: "acf-copy", path: "page_blocks/0/copy", label: "Introductie", value_type: "rich_text", current_value: "<p>Oud</p>", required: true, max_length: 5000 },
            { id: "acf-subtitle", path: "page_blocks/0/subtitle", label: "Subtitel", value_type: "plain_text", current_value: "", required: false, max_length: 180 },
          ],
        },
        {
          id: "cta",
          layout: "cta",
          label: "Contact opnemen",
          semantic_role: "cta",
          fields: [
            { id: "acf-cta-url", path: "page_blocks/1/url", label: "CTA-link", value_type: "url", current_value: "/contact/", required: true, max_length: 2048 },
          ],
        },
      ],
    },
  },
  rendered_html: "",
  job: { state: "completed", progress: 100 },
};

const activeCandidate = {
  id: "candidate-1",
  proposal_group_id: "proposal-group-1",
  base_version_id: "proposal-1",
  generation_mode: "block",
  target_block_id: "hero",
  instruction: "Maak de intro scherper.",
  status: "ready",
  provider: "openrouter",
  model: "model-2",
  prompt_version: "prompt-v2",
  input_tokens: 12,
  output_tokens: 8,
  candidate_package: {
    ...proposal.package,
    title: "DSG versnellingsbak reviseren en herstellen",
    replacements: [
      { field_id: "acf-title", value: "DSG revisie Rotterdam" },
      { field_id: "acf-copy", value: "<p>Nog concretere diagnose en revisie.</p>" },
      { field_id: "acf-cta-url", value: "/contact/" },
    ],
  },
  candidate_rendered_html:
    "<section><h2>Nieuwe versie</h2><p>Nog concretere diagnose en revisie.</p></section>",
};

const attentionProposal = {
  ...proposal,
  state: "needs_attention",
  package: {
    text_replacements: {
      "document:title": "DSG revisie Schiedam",
      "document:slug": "dsg-revisie-schiedam",
      "seo:title": "DSG revisie Schiedam | Specialist",
      "seo:meta_description": "Deskundige DSG revisie in Schiedam door een ervaren transmissiespecialist.",
      "seo:focus_keyword": "dsg revisie schiedam",
      "acf:hero:label": "",
      "acf:hero:copy": "<p>Heldere diagnose en revisie.</p>",
    },
  },
  config_snapshot: {
    content_schema: {
      schema_version: "snapshot-text-v1",
      document_fields: [
        { id: "document:title", path: "post_title", label: "Paginatitel", value_type: "heading", current_value: "", required: true, max_length: 180 },
        { id: "document:slug", path: "post_name", label: "Slug", value_type: "plain_text", current_value: "", required: true, max_length: 160 },
        { id: "seo:title", path: "seo.title", label: "SEO-title", value_type: "seo_title", current_value: "", required: true, max_length: 70 },
        { id: "seo:meta_description", path: "seo.meta_description", label: "Meta description", value_type: "meta_description", current_value: "", required: true, max_length: 170 },
        { id: "seo:focus_keyword", path: "seo.focus_keyword", label: "Focuszoekwoord", value_type: "focus_keyword", current_value: "", required: true, max_length: 160 },
      ],
      blocks: [
        {
          id: "hero",
          layout: "hero_algemeen",
          label: "Hero (algemeen)",
          semantic_role: "hero",
          fields: [
            { id: "acf:hero:label", path: "page_blocks/0/label", label: "Hero-label", value_type: "plain_text", current_value: "", required: true, max_length: 80 },
            { id: "acf:hero:copy", path: "page_blocks/0/copy", label: "Introductie", value_type: "rich_text", current_value: "", required: true, max_length: 5000 },
          ],
        },
      ],
    },
  },
  stages: [
    { name: "template", state: "ready", retry_count: 0 },
    { name: "text", state: "ready", retry_count: 0 },
    { name: "validation", state: "attention", retry_count: 0 },
  ],
  field_errors: {
    "acf:hero:label": "unsafe_html",
  },
  job: {
    state: "completed",
    progress: 100,
    error_message: "7 validation errors for GeneratedBlueprintPackage",
  },
};

describe("PagePackageReview", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    openWindow.mockReset();
    vi.stubGlobal("open", openWindow);
    window.sessionStorage.clear();
    window.sessionStorage.setItem("page-proposal-id:project-1", "proposal-1");
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        return Promise.resolve({ ...proposal, package: JSON.parse(init.body as string).package });
      }
      if (path.endsWith("/approve")) {
        return Promise.resolve({ ...proposal, state: "approved" });
      }
      if (path.endsWith("/draft-job") && init?.method === "POST") {
        return Promise.resolve({
          id: "draft-job-1",
          state: "queued",
          attempt_count: 0,
        });
      }
      if (path.endsWith("/handoffs")) {
        return Promise.resolve({
          handoff: {
            id: "handoff-1",
            project_id: "project-1",
            proposal_version_id: "proposal-1",
            state: "issued",
            expires_at: "2026-07-07T10:00:00Z",
          },
          code: "opaque-code",
          import_url:
            "https://example.com/wp-admin/admin.php?page=wp-fixpilot-import&code=opaque-code&backend=https%3A%2F%2Ffrontend.example%2Fapi%2Fprojects%2Fproject-1%2Fpage-proposals%2Fhandoffs",
        });
      }
      return Promise.resolve(proposal);
    });
  });

  it("shows the selected blueprint and all replacement fields grouped by block", async () => {
    render(<PagePackageReview projectId="project-1" />);

    expect(await screen.findByLabelText("Paginatitel")).toHaveValue(
      "DSG versnellingsbak reviseren",
    );
    expect(screen.getByText("Dienstpagina · versie 2")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Hero (algemeen)" })).toBeVisible();
    expect(screen.getByLabelText("Titel")).toHaveValue("DSG revisie Schiedam");
    expect(screen.getByLabelText("Introductie").tagName).toBe("TEXTAREA");
    expect(screen.getByLabelText("CTA-link").tagName).toBe("SELECT");
    expect(screen.getByText("Afbeeldingen en vormgeving blijven uit de blueprint behouden.")).toBeVisible();
    expect(screen.getByRole("link", { name: "Terug naar kansen" })).toHaveAttribute(
      "href",
      "#opportunities",
    );
  });

  it("shows a full-width preview above editable blocks and shared regeneration actions", async () => {
    render(<PagePackageReview projectId="project-1" />);

    const preview = await screen.findByLabelText("Pagina-voorbeeld");
    expect(preview).toBeVisible();
    expect(preview.closest(".page-package-preview-shell")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Volledig opnieuw genereren" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Blok opnieuw genereren" })).toBeVisible();
    expect(screen.getByLabelText("Extra instructies")).toBeVisible();
  });

  it("shows current and proposed existing-page content and explainable scores", async () => {
    const existingPageProposal = {
      ...attentionProposal,
      source_wordpress_page_id: "wordpress-page-1",
      state: "proposed",
      rendered_html: "<h1>Voorgestelde DSG revisie</h1>",
      field_errors: {},
    };
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.includes("/monitoring?proposal_id=")) {
        return Promise.resolve({
          page: { id: "wordpress-page-1", status: "proposal_ready" },
          latest_sync_at: "2026-08-07T08:00:00Z",
          next_check_at: "2026-08-14T08:00:00Z",
          captured_version: {
            id: "version-1",
            content_hash: "captured-hash",
            snapshot_payload: {},
          },
          live_changed_since_capture: true,
          versions: [
            { id: "version-live", content_hash: "live-hash", observed_at: "2026-08-08T08:00:00Z" },
            { id: "version-1", content_hash: "captured-hash", observed_at: "2026-08-07T08:00:00Z" },
          ],
          scores: [{
            id: "score-live",
            page_version_id: "version-live",
            overall_score: 90,
            factors: [],
            created_at: "2026-08-08T08:00:00Z",
          }, {
            id: "score-current",
            page_version_id: "version-1",
            overall_score: 61,
            factors: [{
              key: "meta_description",
              value: "",
              points: 0,
              max_points: 10,
              explanation: "Meta description needs attention.",
              suggested_action: "Add a meta description.",
              evidence: { value: "" },
            }],
            created_at: "2026-08-07T08:00:00Z",
          }],
          captured_score: {
            id: "score-current",
            page_version_id: "version-1",
            overall_score: 61,
            factors: [{
              key: "meta_description",
              value: "",
              points: 0,
              max_points: 10,
              explanation: "Meta description needs attention.",
              suggested_action: "Add a meta description.",
              evidence: { value: "" },
            }],
            created_at: "2026-08-07T08:00:00Z",
          },
          projected_score: {
            overall_score: 78,
            factors: [{
              key: "meta_description",
              value: "Deskundige DSG revisie in Schiedam.",
              points: 10,
              max_points: 10,
              explanation: "Meta description is present.",
              suggested_action: "",
              evidence: { value: "Deskundige DSG revisie in Schiedam." },
            }],
          },
          recommendations: [],
          events: [],
        });
      }
      if (path.endsWith("/checks") && init?.method === "POST") {
        return Promise.resolve({ version_id: "version-1", version_created: false });
      }
      if (init?.method === "PUT") return Promise.resolve(existingPageProposal);
      return Promise.resolve(existingPageProposal);
    });

    render(<PagePackageReview projectId="project-1" />);

    const preview = await screen.findByLabelText("Pagina-voorbeeld");
    const comparison = await screen.findByRole("heading", {
      name: "Huidig en voorgesteld",
    });
    expect(preview).toBeVisible();
    expect(
      preview.compareDocumentPosition(comparison) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.getByText("Huidige score 61")).toBeVisible();
    expect(screen.getByText("Verwachte score 78")).toBeVisible();
    expect(screen.getByText("Vastgelegde bronversie")).toBeVisible();
    expect(screen.getByRole("status", {
      name: "Live pagina gewijzigd sinds vastlegging",
    })).toBeVisible();
    expect(screen.getByText("Laatste controle")).toBeVisible();
    expect(screen.getByText("Volgende controle")).toBeVisible();
    expect(screen.getByRole("button", { name: "WordPress-concept aanmaken" })).toBeDisabled();
    expect(apiRequest).toHaveBeenCalledWith(
      "/projects/project-1/wordpress-pages/wordpress-page-1/monitoring?proposal_id=proposal-1",
    );

    fireEvent.change(screen.getByLabelText("Hero-label"), {
      target: { value: "DSG-specialist" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Wijzigingen opslaan" }));
    await waitFor(() => expect(
      apiRequest.mock.calls.filter(([path]) => path.includes("/monitoring?proposal_id=")).length,
    ).toBe(2));

    fireEvent.click(screen.getByRole("button", { name: "Nu controleren" }));
    expect(await screen.findByRole("status", {
      name: "De pagina is gecontroleerd.",
    })).toHaveTextContent(
      "De pagina is gecontroleerd.",
    );
  });

  it("saves unsaved edits before approving the exact proposal package", async () => {
    const existingPageProposal = {
      ...attentionProposal,
      source_wordpress_page_id: "wordpress-page-1",
      state: "proposed",
      field_errors: {},
    };
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.includes("/monitoring?proposal_id=")) {
        return Promise.resolve({
          page: { id: "wordpress-page-1", status: "proposal_ready" },
          latest_sync_at: null,
          next_check_at: null,
          captured_version: null,
          captured_score: null,
          live_changed_since_capture: false,
          versions: [],
          scores: [],
          projected_score: null,
          recommendations: [],
          events: [],
        });
      }
      if (init?.method === "PUT") {
        const written = JSON.parse(init.body as string).package.text_replacements;
        return Promise.resolve({
          ...existingPageProposal,
          package: {
            text_replacements: Object.fromEntries(
              Object.entries(written).map(([key, value]) => [
                key,
                (value as { value: string }).value,
              ]),
            ),
          },
        });
      }
      if (path.endsWith("/approve") && init?.method === "POST") {
        return Promise.resolve({ ...existingPageProposal, state: "approved" });
      }
      return Promise.resolve(existingPageProposal);
    });
    render(<PagePackageReview projectId="project-1" />);
    fireEvent.change(await screen.findByLabelText("Hero-label"), {
      target: { value: "Eerst opgeslagen" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Voorstel goedkeuren" }));

    await waitFor(() => {
      const mutations = apiRequest.mock.calls.filter(([, init]) => init?.method);
      expect(mutations.map(([, init]) => init?.method)).toEqual(["PUT", "POST"]);
      expect(mutations[1][0]).toBe(
        "/projects/project-1/page-proposals/proposal-1/approve",
      );
      expect(JSON.parse(mutations[0][1].body as string).package.text_replacements[
        "acf:hero:label"
      ]).toEqual({ value: "Eerst opgeslagen" });
    });
    expect(screen.getByText(/Voorstel goedgekeurd/)).toBeVisible();
  });

  it("does not approve when persisting unsaved edits fails", async () => {
    const existingPageProposal = {
      ...attentionProposal,
      source_wordpress_page_id: "wordpress-page-1",
      state: "proposed",
      field_errors: {},
    };
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.includes("/monitoring?proposal_id=")) return new Promise(() => undefined);
      if (init?.method === "PUT") return Promise.reject(new Error("save failed"));
      return Promise.resolve(existingPageProposal);
    });
    render(<PagePackageReview projectId="project-1" />);
    fireEvent.change(await screen.findByLabelText("Hero-label"), {
      target: { value: "Niet opgeslagen" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Voorstel goedkeuren" }));

    expect(await screen.findByText(
      "Wijzigingen opslaan mislukt. Het voorstel is niet goedgekeurd.",
    )).toBeVisible();
    expect(apiRequest.mock.calls.some(([path]) => path.endsWith("/approve"))).toBe(false);
  });

  it("clears stale monitoring while a saved package refreshes", async () => {
    const existingPageProposal = {
      ...attentionProposal,
      source_wordpress_page_id: "wordpress-page-1",
      state: "proposed",
      field_errors: {},
    };
    let monitoringCalls = 0;
    let resolveRefresh: ((value: unknown) => void) | undefined;
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.includes("/monitoring?proposal_id=")) {
        monitoringCalls += 1;
        if (monitoringCalls === 1) {
          return Promise.resolve({
            page: { id: "wordpress-page-1", status: "proposal_ready" },
            latest_sync_at: null,
            next_check_at: null,
            captured_version: { id: "version-1", content_hash: "hash-1" },
            captured_score: { id: "score-1", page_version_id: "version-1", overall_score: 61, factors: [] },
            live_changed_since_capture: false,
            versions: [],
            scores: [],
            projected_score: { overall_score: 78, factors: [] },
            recommendations: [],
            events: [],
          });
        }
        return new Promise((resolve) => {
          resolveRefresh = resolve;
        });
      }
      if (init?.method === "PUT") return Promise.resolve(existingPageProposal);
      return Promise.resolve(existingPageProposal);
    });
    render(<PagePackageReview projectId="project-1" />);
    expect(await screen.findByText("Huidige score 61")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Wijzigingen opslaan" }));

    expect(await screen.findByRole("status", { name: "Monitoring laden" })).toBeVisible();
    expect(screen.queryByText("Huidige score 61")).not.toBeInTheDocument();
    resolveRefresh?.({
      page: { id: "wordpress-page-1", status: "proposal_ready" },
      latest_sync_at: null,
      next_check_at: null,
      captured_version: null,
      captured_score: null,
      live_changed_since_capture: false,
      versions: [],
      scores: [],
      projected_score: null,
      recommendations: [],
      events: [],
    });
  });

  it("reports a committed check separately when refreshing results fails", async () => {
    const existingPageProposal = {
      ...attentionProposal,
      source_wordpress_page_id: "wordpress-page-1",
      state: "proposed",
      field_errors: {},
    };
    const monitoringResponse = {
      page: { id: "wordpress-page-1", status: "proposal_ready" },
      latest_sync_at: "2026-08-07T08:00:00Z",
      next_check_at: "2026-08-14T08:00:00Z",
      captured_version: { id: "version-1", content_hash: "hash-1" },
      captured_score: null,
      live_changed_since_capture: false,
      versions: [],
      scores: [],
      projected_score: null,
      recommendations: [],
      events: [],
    };
    let monitoringCalls = 0;
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.endsWith("/checks") && init?.method === "POST") {
        return Promise.resolve({ version_id: "version-1", version_created: false });
      }
      if (path.includes("/monitoring?proposal_id=")) {
        monitoringCalls += 1;
        if (monitoringCalls === 2) {
          return Promise.reject(new Error("refresh failed"));
        }
        return Promise.resolve(monitoringResponse);
      }
      return Promise.resolve(existingPageProposal);
    });
    render(<PagePackageReview projectId="project-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "Nu controleren" }));

    expect(await screen.findByText(
      "De pagina is gecontroleerd, maar de vernieuwde resultaten konden niet worden geladen.",
    )).toBeVisible();
    expect(screen.queryByText("Pagina controleren mislukt.")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Monitoring laden")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Paginatijdlijn" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Resultaten opnieuw laden" }));

    expect(await screen.findByRole("heading", { name: "Paginatijdlijn" })).toBeVisible();
    expect(monitoringCalls).toBe(3);
  });

  it("reports check failure when the manual check POST fails", async () => {
    const existingPageProposal = {
      ...attentionProposal,
      source_wordpress_page_id: "wordpress-page-1",
      state: "proposed",
      field_errors: {},
    };
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.endsWith("/checks") && init?.method === "POST") {
        return Promise.reject(new Error("check failed"));
      }
      if (path.includes("/monitoring?proposal_id=")) {
        return Promise.resolve({
          page: { id: "wordpress-page-1", status: "proposal_ready" },
          latest_sync_at: null,
          next_check_at: null,
          captured_version: null,
          captured_score: null,
          live_changed_since_capture: false,
          versions: [],
          scores: [],
          projected_score: null,
          recommendations: [],
          events: [],
        });
      }
      return Promise.resolve(existingPageProposal);
    });
    render(<PagePackageReview projectId="project-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "Nu controleren" }));

    expect(await screen.findByText("Pagina controleren mislukt.")).toBeVisible();
    expect(screen.queryByRole("button", {
      name: "Resultaten opnieuw laden",
    })).not.toBeInTheDocument();
  });

  it("shows a saved candidate compare flow and can accept or discard it", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/accept")) {
        return Promise.resolve({
          current_version: {
            ...proposal,
            id: "proposal-2",
            version_number: 2,
            package: activeCandidate.candidate_package,
            rendered_html: activeCandidate.candidate_rendered_html,
          },
          revoked_handoff_ids: [],
        });
      }
      if (path.endsWith("/discard")) {
        return Promise.resolve({
          candidate: { ...activeCandidate, status: "discarded" },
        });
      }
      return Promise.resolve({ ...proposal, active_candidate: activeCandidate });
    });

    render(<PagePackageReview projectId="project-1" />);

    expect(await screen.findByText("Vergelijk gegenereerde versie")).toBeVisible();
    expect(screen.getByRole("button", { name: "Deze versie gebruiken" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Kandidaat verwerpen" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Deze versie gebruiken" }));
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/project-1/page-proposals/candidates/candidate-1/accept",
        { method: "POST" },
      ),
    );

    apiRequest.mockClear();
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/discard")) {
        return Promise.resolve({
          candidate: { ...activeCandidate, status: "discarded" },
        });
      }
      return Promise.resolve({ ...proposal, active_candidate: activeCandidate });
    });

    render(<PagePackageReview projectId="project-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Kandidaat verwerpen" }));
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/project-1/page-proposals/candidates/candidate-1/discard",
        { method: "POST" },
      ),
    );
  });

  it("adds an optional schema field that AI left empty", async () => {
    render(<PagePackageReview projectId="project-1" />);
    fireEvent.change(await screen.findByLabelText("Subtitel"), {
      target: { value: "Specialist in Schiedam" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Wijzigingen opslaan" }));

    await waitFor(() => {
      const update = apiRequest.mock.calls.find(([, init]) => init?.method === "PUT");
      expect(JSON.parse(update?.[1].body as string).package.replacements).toContainEqual({
        field_id: "acf-subtitle",
        value: "Specialist in Schiedam",
      });
    });
  });

  it("keeps the generation status visible while the persisted job runs", async () => {
    apiRequest.mockResolvedValue({
      ...proposal,
      state: "generating",
      package: {},
      job: { state: "running", progress: 35 },
    });

    render(<PagePackageReview projectId="project-1" />);

    expect(await screen.findByText(/Dit bericht blijft staan/)).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Paginapakket wordt gemaakt" }),
    ).toBeVisible();
  });

  it("keeps successful text and shows only the invalid field recovery", async () => {
    apiRequest.mockResolvedValue(attentionProposal);

    render(<PagePackageReview projectId="project-1" />);

    expect(await screen.findByText("Tekst gereed")).toBeVisible();
    expect(screen.getByText("Hero-label bevat niet-toegestane opmaak")).toBeVisible();
    expect(screen.getByLabelText("Paginatitel")).toHaveValue("DSG revisie Schiedam");
    expect(screen.getByRole("button", { name: "Waarde aanpassen" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Voorstel goedkeuren" })).toBeDisabled();
    expect(screen.queryByText(/validation errors for/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Waarde aanpassen" }));
    expect(screen.getByLabelText("Hero-label")).toHaveFocus();
  });

  it("retries validation without replacing the generated text", async () => {
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.endsWith("/stages/validation/retry") && init?.method === "POST") {
        return Promise.resolve({
          ...attentionProposal,
          state: "proposed",
          stages: attentionProposal.stages.map((stage) => (
            stage.name === "validation" ? { ...stage, state: "ready" } : stage
          )),
          field_errors: {},
        });
      }
      return Promise.resolve(attentionProposal);
    });

    render(<PagePackageReview projectId="project-1" />);
    fireEvent.click(await screen.findByRole("button", {
      name: "Validatie opnieuw uitvoeren",
    }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/projects/project-1/page-proposals/proposal-1/stages/validation/retry",
      { method: "POST" },
    ));
    expect(screen.getByLabelText("Paginatitel")).toHaveValue("DSG revisie Schiedam");
    expect(screen.getByRole("button", { name: "Wijzigingen opslaan" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Voorstel goedkeuren" })).toBeEnabled();
  });

  it("saves a local correction before retrying validation", async () => {
    const correctedPackage = {
      text_replacements: {
        ...attentionProposal.package.text_replacements,
        "acf:hero:label": "DSG-specialist",
      },
    };
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        return Promise.resolve({
          ...attentionProposal,
          state: "proposed",
          package: correctedPackage,
          field_errors: {},
          stages: attentionProposal.stages.map((stage) => (
            stage.name === "validation" ? { ...stage, state: "ready" } : stage
          )),
        });
      }
      if (path.endsWith("/stages/validation/retry") && init?.method === "POST") {
        return Promise.resolve({
          ...attentionProposal,
          state: "proposed",
          package: correctedPackage,
          field_errors: {},
        });
      }
      return Promise.resolve(attentionProposal);
    });

    render(<PagePackageReview projectId="project-1" />);
    fireEvent.change(await screen.findByLabelText("Hero-label"), {
      target: { value: "DSG-specialist" },
    });
    fireEvent.click(screen.getByRole("button", {
      name: "Validatie opnieuw uitvoeren",
    }));

    await waitFor(() => {
      const methods = apiRequest.mock.calls
        .map(([, init]) => init?.method)
        .filter(Boolean);
      expect(methods).toEqual(["PUT"]);
    });
    expect(screen.getByLabelText("Hero-label")).toHaveValue("DSG-specialist");
    expect(screen.getByText("Wijzigingen opgeslagen en gevalideerd.")).toBeVisible();
  });

  it("follows the new proposal version after retrying failed text", async () => {
    const failedText = {
      ...attentionProposal,
      state: "failed",
      stages: attentionProposal.stages.map((stage) => (
        stage.name === "text" ? { ...stage, state: "failed" } : stage
      )),
    };
    let activeProposal: Record<string, unknown> = failedText;
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.endsWith("/stages/text/retry") && init?.method === "POST") {
        activeProposal = {
          ...attentionProposal,
          id: "proposal-2",
          state: "proposed",
          field_errors: {},
          stages: attentionProposal.stages.map((stage) => ({
            ...stage,
            state: "ready",
          })),
        };
        return Promise.resolve({
          ...activeProposal,
          state: "generating",
          package: {},
        });
      }
      return Promise.resolve(activeProposal);
    });

    render(<PagePackageReview projectId="project-1" />);
    fireEvent.click(await screen.findByRole("button", {
      name: "Tekst opnieuw genereren",
    }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/projects/project-1/page-proposals/proposal-1/stages/text/retry",
      { method: "POST" },
    ));
    expect(window.sessionStorage.getItem("page-proposal-id:project-1")).toBe(
      "proposal-2",
    );
    expect(await screen.findByText("Te beoordelen")).toBeVisible();
  });

  it("submits a corrected snapshot field without dropping successful text", async () => {
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        return Promise.resolve({
          ...attentionProposal,
          state: "proposed",
          package: {
            text_replacements: Object.fromEntries(
              Object.entries(
                JSON.parse(init.body as string).package.text_replacements,
              ).map(([fieldId, value]) => [
                fieldId,
                (value as { value: string }).value,
              ]),
            ),
          },
          field_errors: {},
        });
      }
      return Promise.resolve(attentionProposal);
    });

    render(<PagePackageReview projectId="project-1" />);
    fireEvent.change(await screen.findByLabelText("Hero-label"), {
      target: { value: "DSG-specialist" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Wijzigingen opslaan" }));

    await waitFor(() => {
      const update = apiRequest.mock.calls.find(([, init]) => init?.method === "PUT");
      const replacements = JSON.parse(
        update?.[1].body as string,
      ).package.text_replacements;
      expect(replacements["acf:hero:label"]).toEqual({ value: "DSG-specialist" });
      expect(replacements["document:title"]).toEqual({ value: "DSG revisie Schiedam" });
    });
  });

  it("allows approval when only an optional snapshot field is invalid", async () => {
    const optionalError = {
      ...attentionProposal,
      state: "needs_attention",
      field_errors: {
        "acf:hero:optional": "unsafe_html",
      },
      config_snapshot: {
        content_schema: {
          ...attentionProposal.config_snapshot.content_schema,
          blocks: [{
            ...attentionProposal.config_snapshot.content_schema.blocks[0],
            fields: [
              ...attentionProposal.config_snapshot.content_schema.blocks[0].fields,
              {
                id: "acf:hero:optional",
                path: "page_blocks/0/optional",
                label: "Extra label",
                value_type: "plain_text",
                current_value: "",
                required: false,
                max_length: 80,
              },
            ],
          }],
        },
      },
    };
    apiRequest.mockResolvedValue(optionalError);

    render(<PagePackageReview projectId="project-1" />);

    expect(await screen.findByText("Extra label bevat niet-toegestane opmaak")).toBeVisible();
    expect(screen.getByRole("button", { name: "Voorstel goedkeuren" })).toBeEnabled();
    expect(screen.getByLabelText("Extra label")).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Waarde aanpassen" }));
    expect(screen.getByLabelText("Extra label")).toHaveFocus();
  });

  it("replaces raw API validation details with a bounded action error", async () => {
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.endsWith("/stages/validation/retry") && init?.method === "POST") {
        return Promise.reject(new Error(
          "7 validation errors for GeneratedBlueprintPackage extra_forbidden",
        ));
      }
      return Promise.resolve(attentionProposal);
    });

    render(<PagePackageReview projectId="project-1" />);
    fireEvent.click(await screen.findByRole("button", {
      name: "Validatie opnieuw uitvoeren",
    }));

    expect(await screen.findByText("Opnieuw uitvoeren mislukt.")).toBeVisible();
    expect(screen.queryByText(/validation errors for/i)).not.toBeInTheDocument();
  });

  it("replaces short raw provider details with the action fallback", async () => {
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.endsWith("/stages/validation/retry") && init?.method === "POST") {
        return Promise.reject(new Error(
          "Value error, HTML is not allowed in plain text fields",
        ));
      }
      return Promise.resolve(attentionProposal);
    });

    render(<PagePackageReview projectId="project-1" />);
    fireEvent.click(await screen.findByRole("button", {
      name: "Validatie opnieuw uitvoeren",
    }));

    expect(await screen.findByText("Opnieuw uitvoeren mislukt.")).toBeVisible();
    expect(screen.queryByText(/HTML is not allowed/i)).not.toBeInTheDocument();
  });

  it("does not mark manual approval complete while attention is required", async () => {
    apiRequest.mockResolvedValue(attentionProposal);

    render(<PagePackageReview projectId="project-1" />);

    const step = (await screen.findByText("Handmatig goedgekeurd")).closest("li");
    expect(step).not.toHaveClass("complete");
  });

  it("compares a generated snapshot candidate without legacy title fields", async () => {
    apiRequest.mockResolvedValue({
      ...attentionProposal,
      state: "approved",
      field_errors: {},
      package: {
        text_replacements: {
          ...attentionProposal.package.text_replacements,
          "acf:hero:label": "Huidige hero-inhoud",
        },
      },
      active_candidate: {
        ...activeCandidate,
        candidate_package: {
          text_replacements: {
            ...attentionProposal.package.text_replacements,
            "document:title": "Nieuwe DSG snapshotversie",
          },
        },
      },
    });

    render(<PagePackageReview projectId="project-1" />);

    expect(await screen.findByText("Vergelijk gegenereerde versie")).toBeVisible();
    expect(screen.getAllByText("DSG revisie Schiedam").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Nieuwe DSG snapshotversie").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Hero-label")).toHaveLength(2);
    expect(screen.getByText("Huidige hero-inhoud")).toBeVisible();
    expect(screen.getByText("Leeg")).toBeVisible();
  });

  it("does not offer comparison actions for a failed candidate", async () => {
    apiRequest.mockResolvedValue({
      ...attentionProposal,
      state: "approved",
      field_errors: {},
      active_candidate: {
        ...activeCandidate,
        status: "failed",
      },
    });

    render(<PagePackageReview projectId="project-1" />);

    expect(await screen.findByText("Nieuwe versie genereren mislukt.")).toBeVisible();
    expect(screen.queryByText("Vergelijk gegenereerde versie")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", {
      name: "Deze versie gebruiken",
    })).not.toBeInTheDocument();
  });

  it("does not offer comparison actions while a candidate is generating", async () => {
    apiRequest.mockResolvedValue({
      ...attentionProposal,
      state: "approved",
      field_errors: {},
      active_candidate: {
        ...activeCandidate,
        status: "generating",
        candidate_package: undefined,
      },
    });

    render(<PagePackageReview projectId="project-1" />);

    expect(await screen.findByText("Paginapakket beoordelen")).toBeVisible();
    expect(screen.queryByText("Vergelijk gegenereerde versie")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", {
      name: "Deze versie gebruiken",
    })).not.toBeInTheDocument();
  });

  it("saves, approves, and queues a WordPress draft without opening a window", async () => {
    render(<PagePackageReview projectId="project-1" />);
    const title = await screen.findByLabelText("Paginatitel");
    fireEvent.change(title, { target: { value: "Aangepaste DSG pagina" } });

    expect(
      screen.getByRole("button", { name: "WordPress-concept aanmaken" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Wijzigingen opslaan" }));
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/project-1/page-proposals/proposal-1",
        expect.objectContaining({ method: "PUT" }),
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "Voorstel goedkeuren" }));

    expect(
      await screen.findByRole("button", { name: "WordPress-concept aanmaken" }),
    ).toBeEnabled();
    fireEvent.click(
      screen.getByRole("button", { name: "WordPress-concept aanmaken" }),
    );
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/project-1/page-proposals/proposal-1/draft-job",
        { method: "POST" },
      ),
    );
    expect(await screen.findByText("Wachten op WordPress")).toBeVisible();
    expect(openWindow).not.toHaveBeenCalled();
  });

  it("keeps manual import available after an outbound failure", async () => {
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.endsWith("/handoffs") && init?.method === "POST") {
        return Promise.resolve({
          handoff: { id: "handoff-1", state: "issued" },
          code: "opaque-code",
          import_url: "https://example.com/wp-admin/admin.php?page=wp-fixpilot-import",
        });
      }
      return Promise.resolve({
        ...proposal,
        state: "approved",
        draft_job: {
          id: "draft-job-1",
          state: "failed",
          error_message: "Blueprint gewijzigd",
          attempt_count: 1,
        },
      });
    });

    render(<PagePackageReview projectId="project-1" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Handmatige import openen" }),
    );

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/project-1/page-proposals/proposal-1/handoffs",
        { method: "POST" },
      ),
    );
  });

  it("retries a failed outbound draft job", async () => {
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.endsWith("/draft-job") && init?.method === "POST") {
        return Promise.resolve({
          id: "draft-job-1",
          state: "queued",
          attempt_count: 1,
        });
      }
      return Promise.resolve({
        ...proposal,
        state: "approved",
        draft_job: {
          id: "draft-job-1",
          state: "failed",
          error_message: "Adapter tijdelijk niet beschikbaar",
          attempt_count: 1,
        },
      });
    });

    render(<PagePackageReview projectId="project-1" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Opnieuw proberen" }),
    );

    expect(await screen.findByText("Wachten op WordPress")).toBeVisible();
    expect(apiRequest).toHaveBeenCalledWith(
      "/projects/project-1/page-proposals/proposal-1/draft-job",
      { method: "POST" },
    );
  });

  it("rechecks a completed draft job without changing its WordPress URL", async () => {
    const wordpressEditUrl = "https://example.com/wp-admin/post.php?post=12323&action=edit";
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.endsWith("/draft-job") && init?.method === "POST") {
        return Promise.resolve({
          id: "draft-job-1",
          state: "completed",
          wordpress_edit_url: wordpressEditUrl,
          attempt_count: 1,
        });
      }
      return Promise.resolve({
        ...proposal,
        state: "draft_created",
        wordpress_edit_url: wordpressEditUrl,
        draft_job: {
          id: "draft-job-1",
          state: "completed",
          wordpress_edit_url: wordpressEditUrl,
          attempt_count: 1,
        },
      });
    });

    render(<PagePackageReview projectId="project-1" />);
    const editLink = await screen.findByRole("link", {
      name: "Concept openen in WordPress",
    });
    expect(editLink).toHaveAttribute("href", wordpressEditUrl);

    fireEvent.click(
      screen.getByRole("button", { name: "Conceptstatus opnieuw controleren" }),
    );

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/project-1/page-proposals/proposal-1/draft-job",
        { method: "POST" },
      ),
    );
    expect(await screen.findByText("WordPress-concept gecontroleerd.")).toBeVisible();
    expect(screen.getByRole("link", {
      name: "Concept openen in WordPress",
    })).toHaveAttribute("href", wordpressEditUrl);
  });
});

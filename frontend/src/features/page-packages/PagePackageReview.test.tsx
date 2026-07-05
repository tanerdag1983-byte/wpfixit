import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PagePackageReview } from "./PagePackageReview";

const apiRequest = vi.fn();

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

describe("PagePackageReview", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    window.sessionStorage.clear();
    window.sessionStorage.setItem("page-proposal-id:project-1", "proposal-1");
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        return Promise.resolve({ ...proposal, package: JSON.parse(init.body as string).package });
      }
      if (path.endsWith("/approve")) {
        return Promise.resolve({ ...proposal, state: "approved" });
      }
      if (path.endsWith("/create-draft")) {
        return Promise.resolve({
          ...proposal,
          state: "draft_created",
          wordpress_edit_url: "https://example.com/wp-admin/post.php?post=987",
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

  it("saves edits and requires approval before draft creation", async () => {
    render(<PagePackageReview projectId="project-1" />);
    const title = await screen.findByLabelText("Paginatitel");
    fireEvent.change(title, { target: { value: "Aangepaste DSG pagina" } });

    expect(screen.getByRole("button", { name: "WordPress-concept aanmaken" })).toBeDisabled();
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
    expect(
      await screen.findByRole("link", { name: "Concept openen in WordPress" }),
    ).toHaveAttribute(
      "href",
      "https://example.com/wp-admin/post.php?post=987",
    );
  });
});

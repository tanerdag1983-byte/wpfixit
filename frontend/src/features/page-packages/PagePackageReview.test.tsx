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
    hero_title: "DSG versnellingsbak reviseren",
    introduction_html: "<p>Heldere diagnose en revisie.</p>",
    sections: [
      { heading: "Klachten", body_html: "<p>Schokken en slippen.</p>" },
      { heading: "Werkwijze", body_html: "<p>We starten met diagnose.</p>" },
    ],
    faq: [
      { question: "Hoe lang duurt revisie?", answer_html: "<p>Na diagnose.</p>" },
      { question: "Krijg ik een prijs?", answer_html: "<p>Vooraf besproken.</p>" },
    ],
    cta: {
      title: "Laat uw DSG controleren",
      body_html: "<p>Plan een diagnose.</p>",
      button_label: "Afspraak maken",
      button_url: "/contact/",
    },
    internal_links: [
      { anchor: "contact", url: "https://example.com/contact/" },
    ],
  },
  rendered_html: "<h1>DSG versnellingsbak reviseren</h1><script>alert(1)</script>",
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

  it("loads every page-package section and sanitizes the preview", async () => {
    render(<PagePackageReview projectId="project-1" />);

    expect(await screen.findByLabelText("Paginatitel")).toHaveValue(
      "DSG versnellingsbak reviseren",
    );
    expect(screen.getByDisplayValue("Klachten")).toBeVisible();
    expect(screen.getByDisplayValue("Hoe lang duurt revisie?")).toBeVisible();
    expect(screen.getByDisplayValue("Afspraak maken")).toBeVisible();
    expect(screen.getByRole("link", { name: "Terug naar kansen" })).toHaveAttribute(
      "href",
      "#opportunities",
    );
    expect(screen.getByLabelText("Pagina-voorbeeld").innerHTML).not.toContain("script");
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

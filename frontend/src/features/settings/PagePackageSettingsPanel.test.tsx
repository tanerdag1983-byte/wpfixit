import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PagePackageSettingsPanel } from "./PagePackageSettingsPanel";

const apiRequest = vi.fn();

vi.mock("../../lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

describe("PagePackageSettingsPanel", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (!init && path.endsWith("/page-package-settings")) {
        return Promise.resolve({
          configured: false,
          validation_state: "unconfigured",
        });
      }
      if (!init && path.endsWith("/wordpress-pages")) {
        return Promise.resolve({
          count: 1,
          items: [
            {
              id: "template-1",
              wordpress_object_id: 701,
              title: "Dienst template",
              url: "https://example.com/dienst-template/",
            },
          ],
        });
      }
      if (!init && path.endsWith("/page-package-settings/options")) {
        return Promise.resolve({ builders: ["gutenberg", "elementor", "acf"], seo_plugin: "yoast" });
      }
      if (path.endsWith("/inspect-template")) {
        return Promise.resolve({
          builder: "acf",
          seo_plugin: "yoast",
          template_hash: "hash-1",
          slots: [
            { path: "acf-block:field_page_blocks:0", label: "Paginablokken · Hero (algemeen)", value_type: "html", preview: "Abarth Versnellingsbak Reparatie Schiedam · Specialistische diagnose en reparatie." },
            { path: "acf-block:field_page_blocks:1", label: "Paginablokken · Symptom Pain Section", value_type: "html", preview: "Herkent u deze klachten? · Knipperende N en schakelproblemen." },
            { path: "acf-block:field_page_blocks:2", label: "Paginablokken · Team Section", value_type: "html", preview: "Ons transmissieteam in Schiedam." },
            { path: "acf-block:field_page_blocks:3", label: "Paginablokken · Waarom SHM", value_type: "html", preview: "Waarom kiezen voor SHM Transmissie?" },
            { path: "acf-block:field_page_blocks:4", label: "Paginablokken · FAQ Section", value_type: "html", preview: "Veelgestelde vragen over Abarth reparatie." },
          ],
        });
      }
      return Promise.resolve({
        configured: true,
        builder: "elementor",
        template_wordpress_page_id: "template-1",
        seo_plugin: "yoast",
        slot_mapping: {},
        validation_state: "unvalidated",
      });
    });
  });

  it("saves the builder and template separately for the project", async () => {
    render(<PagePackageSettingsPanel projectId="project-1" />);

    fireEvent.change(await screen.findByLabelText("Page builder"), {
      target: { value: "elementor" },
    });
    fireEvent.change(screen.getByLabelText("Standaard templatepagina"), {
      target: { value: "template-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Paginapakket opslaan" }));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/project-1/page-package-settings",
        expect.objectContaining({
          method: "PUT",
          body: expect.stringContaining('"builder":"elementor"'),
        }),
      ),
    );
  });

  it("loads discovered template blocks for one-time mapping", async () => {
    render(<PagePackageSettingsPanel projectId="project-1" />);
    fireEvent.change(await screen.findByLabelText("Page builder"), {
      target: { value: "elementor" },
    });
    fireEvent.change(screen.getByLabelText("Standaard templatepagina"), {
      target: { value: "template-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Paginapakket opslaan" }));
    await screen.findByText("Paginapakket is opgeslagen en moet worden gevalideerd.");
    fireEvent.click(screen.getByRole("button", { name: "Blokken ophalen" }));

    fireEvent.click(await screen.findByText("AI-inhoud aan templateblokken koppelen"));
    const heroSelect = await screen.findByLabelText("Hero-titel");
    expect(heroSelect).toBeVisible();
    expect(heroSelect).toHaveTextContent("Paginablokken · Hero (algemeen)");
    expect(screen.getByRole("heading", { name: "Hero (algemeen)" })).toBeVisible();
    expect(screen.getByText("Abarth Versnellingsbak Reparatie Schiedam · Specialistische diagnose en reparatie.")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Symptom Pain Section" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Team Section" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Waarom SHM" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "FAQ Section" })).toBeVisible();
    expect(screen.getByText("5 echte templateblokken gevonden.")).toBeVisible();
  });

  it("allows global CTA content to remain unmapped", async () => {
    render(<PagePackageSettingsPanel projectId="project-1" />);
    fireEvent.change(await screen.findByLabelText("Page builder"), {
      target: { value: "acf" },
    });
    fireEvent.change(screen.getByLabelText("Standaard templatepagina"), {
      target: { value: "template-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Paginapakket opslaan" }));
    await screen.findByText("Paginapakket is opgeslagen en moet worden gevalideerd.");
    fireEvent.click(screen.getByRole("button", { name: "Blokken ophalen" }));

    fireEvent.click(await screen.findByText("AI-inhoud aan templateblokken koppelen"));
    fireEvent.change(await screen.findByLabelText("Hero-titel"), {
      target: { value: "acf-block:field_page_blocks:0" },
    });
    fireEvent.change(screen.getByLabelText("Introductie"), {
      target: { value: "acf-block:field_page_blocks:0" },
    });
    fireEvent.change(screen.getByLabelText("Hoofdinhoud"), {
      target: { value: "acf-block:field_page_blocks:1" },
    });
    fireEvent.change(screen.getByLabelText("FAQ"), {
      target: { value: "acf-block:field_page_blocks:2" },
    });

    expect(screen.getByRole("button", { name: "Paginapakket valideren" })).toBeEnabled();
    expect(screen.getByLabelText("CTA-titel (optioneel)")).toHaveValue("");
    expect(screen.getByLabelText("CTA-tekst (optioneel)")).toHaveValue("");
  });

  it("keeps duplicate mappings disabled for non-ACF builders", async () => {
    render(<PagePackageSettingsPanel projectId="project-1" />);
    fireEvent.change(await screen.findByLabelText("Page builder"), {
      target: { value: "elementor" },
    });
    fireEvent.change(screen.getByLabelText("Standaard templatepagina"), {
      target: { value: "template-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Paginapakket opslaan" }));
    await screen.findByText("Paginapakket is opgeslagen en moet worden gevalideerd.");
    fireEvent.click(screen.getByRole("button", { name: "Blokken ophalen" }));
    fireEvent.click(await screen.findByText("AI-inhoud aan templateblokken koppelen"));

    for (const label of [
      "Hero-titel",
      "Introductie",
      "Hoofdinhoud",
      "FAQ",
      "CTA-titel (optioneel)",
      "CTA-tekst (optioneel)",
    ]) {
      fireEvent.change(screen.getByLabelText(label), {
        target: { value: "acf-block:field_page_blocks:0" },
      });
    }

    expect(screen.getByRole("button", { name: "Paginapakket valideren" })).toBeDisabled();
  });

  it("allows unique classic ACF fields next to duplicated ACF blocks", async () => {
    apiRequest
      .mockImplementationOnce(() => Promise.resolve({
        configured: true,
        builder: "acf",
        template_wordpress_page_id: "template-1",
        seo_plugin: "yoast",
        slot_mapping: {
          hero_title: "acf-block:field_page_blocks:0",
          introduction: "acf-block:field_page_blocks:0",
          main_content: "acf:field_summary",
          faq: "acf-block:field_page_blocks:2",
          cta_title: "acf-block:field_page_blocks:3",
          cta_text: "acf-block:field_page_blocks:3",
        },
        validation_state: "unvalidated",
      }))
      .mockImplementationOnce(() => Promise.resolve({ items: [] }))
      .mockImplementationOnce(() => Promise.resolve({ builders: ["acf"], seo_plugin: "yoast" }));

    render(<PagePackageSettingsPanel projectId="project-1" />);

    expect(await screen.findByRole("button", { name: "Paginapakket valideren" })).toBeEnabled();
  });
});

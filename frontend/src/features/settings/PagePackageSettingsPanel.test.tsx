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
        return Promise.resolve({ builders: ["gutenberg", "elementor"], seo_plugin: "yoast" });
      }
      if (path.endsWith("/inspect-template")) {
        return Promise.resolve({
          builder: "elementor",
          seo_plugin: "yoast",
          template_hash: "hash-1",
          slots: [
            { path: "element:hero:title", label: "Hero", value_type: "text" },
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

    const heroSelect = await screen.findByLabelText("Hero-titel");
    expect(heroSelect).toBeVisible();
    expect(heroSelect).toHaveTextContent("Hero");
  });
});

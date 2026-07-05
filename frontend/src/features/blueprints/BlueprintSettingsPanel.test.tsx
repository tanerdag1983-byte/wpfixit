import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BlueprintSettingsPanel } from "./BlueprintSettingsPanel";

const apiRequest = vi.fn();

vi.mock("../../lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

const blueprint = {
  id: "blueprint-1",
  name: "Dienstpagina",
  page_type: "service",
  source_wordpress_page_id: "page-19",
  wordpress_blueprint_id: 901,
  builder: "acf",
  seo_plugin: "yoast",
  version: 1,
  structure_hash: "hash-v1",
  state: "ready",
  is_default_for_page_type: false,
  supersedes_id: null,
  content_schema: {
    schema_version: "blueprint-v1",
    blocks: [
      {
        id: "hero",
        layout: "hero_algemeen",
        label: "Hero (algemeen)",
        semantic_role: "hero",
        fields: [
          {
            id: "hero-title",
            path: "page_blocks/0/title",
            label: "Titel",
            value_type: "heading",
            current_value: "Transmissie revisie",
            required: true,
            max_length: 180,
          },
        ],
      },
      {
        id: "symptoms",
        layout: "symptoms",
        label: "Symptomen",
        semantic_role: "benefits",
        fields: [
          {
            id: "symptoms-copy",
            path: "page_blocks/1/copy",
            label: "Tekst",
            value_type: "rich_text",
            current_value: "Herkent u deze klachten?",
            required: true,
            max_length: 5000,
          },
        ],
      },
    ],
  },
};

describe("BlueprintSettingsPanel", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (!init && path.endsWith("/page-blueprints")) {
        return Promise.resolve({ items: [] });
      }
      if (!init && path.endsWith("/wordpress-pages")) {
        return Promise.resolve({
          items: [
            {
              id: "page-19",
              wordpress_object_id: 19,
              title: "Algemeen productdetail",
              url: "https://example.test/algemeen-productdetail/",
            },
          ],
        });
      }
      if (init?.method === "POST" && path.endsWith("/page-blueprints")) {
        return Promise.resolve(blueprint);
      }
      return Promise.resolve(blueprint);
    });
  });

  it("creates a blueprint and shows its grouped blocks", async () => {
    render(<BlueprintSettingsPanel projectId="project-1" />);

    fireEvent.change(await screen.findByLabelText("Blueprintnaam"), {
      target: { value: "Dienstpagina" },
    });
    fireEvent.change(screen.getByLabelText("Paginatype"), {
      target: { value: "service" },
    });
    fireEvent.change(screen.getByLabelText("Referentiepagina"), {
      target: { value: "page-19" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Blueprint maken" }));

    expect(await screen.findByText("Hero (algemeen)")).toBeVisible();
    expect(screen.getByText("Symptomen")).toBeVisible();
    expect(screen.getAllByText("Klaar voor conceptpagina's")).toHaveLength(2);
    expect(apiRequest).toHaveBeenCalledWith(
      "/projects/project-1/page-blueprints",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          name: "Dienstpagina",
          page_type: "service",
          source_wordpress_page_id: "page-19",
        }),
      }),
    );
  });

  it("reports managed-blueprint availability to hide legacy mappings", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/page-blueprints")) {
        return Promise.resolve({ items: [blueprint] });
      }
      return Promise.resolve({ items: [] });
    });
    const onAvailabilityChange = vi.fn();

    render(
      <BlueprintSettingsPanel
        projectId="project-1"
        onAvailabilityChange={onAvailabilityChange}
      />,
    );

    await waitFor(() => expect(onAvailabilityChange).toHaveBeenCalledWith(true));
    expect(screen.queryByText(/oude paginapakket/)).not.toBeInTheDocument();
  });

  it("keeps registry state when WordPress inventory fails", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/page-blueprints")) {
        return Promise.resolve({ items: [blueprint] });
      }
      return Promise.reject(new Error("Inventory niet bereikbaar"));
    });
    const onAvailabilityChange = vi.fn();

    render(
      <BlueprintSettingsPanel
        projectId="project-1"
        onAvailabilityChange={onAvailabilityChange}
      />,
    );

    expect(await screen.findByText("Hero (algemeen)")).toBeVisible();
    expect(onAvailabilityChange).toHaveBeenCalledWith(true);
    expect(screen.getByText("Inventory niet bereikbaar")).toBeVisible();
  });

  it("reloads persisted stale state after validation fails", async () => {
    const stale = { ...blueprint, state: "stale" };
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (!init && path.endsWith("/page-blueprints")) {
        return Promise.resolve({ items: [blueprint] });
      }
      if (!init && path.endsWith("/wordpress-pages")) {
        return Promise.resolve({ items: [] });
      }
      if (init?.method === "POST" && path.endsWith("/validate")) {
        return Promise.reject(new Error("Blueprint structure has changed"));
      }
      if (!init && path.endsWith("/page-blueprints/blueprint-1")) {
        return Promise.resolve(stale);
      }
      return Promise.resolve(blueprint);
    });

    render(<BlueprintSettingsPanel projectId="project-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Valideren" }));

    expect(await screen.findAllByText("Nieuwe versie nodig")).toHaveLength(2);
    expect(screen.getByText("Blueprint structure has changed")).toBeVisible();
  });

  it("clears the previous registry immediately when the project changes", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path.includes("project-1") && path.endsWith("/page-blueprints")) {
        return Promise.resolve({ items: [blueprint] });
      }
      if (path.includes("project-2")) return new Promise(() => undefined);
      return Promise.resolve({ items: [] });
    });
    const { rerender } = render(<BlueprintSettingsPanel projectId="project-1" />);
    expect(await screen.findByText("Hero (algemeen)")).toBeVisible();

    rerender(<BlueprintSettingsPanel projectId="project-2" />);

    await waitFor(() =>
      expect(screen.queryByText("Hero (algemeen)")).not.toBeInTheDocument(),
    );
  });

  it("ignores a completed mutation after switching projects", async () => {
    let finishCreate: ((value: typeof blueprint) => void) | undefined;
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (!init && path.includes("project-1") && path.endsWith("/page-blueprints")) {
        return Promise.resolve({ items: [] });
      }
      if (!init && path.includes("project-1") && path.endsWith("/wordpress-pages")) {
        return Promise.resolve({ items: [{ id: "page-19", title: "Bron", url: "/bron/" }] });
      }
      if (init?.method === "POST" && path.includes("project-1")) {
        return new Promise((resolve) => { finishCreate = resolve; });
      }
      if (!init && path.includes("project-2") && path.endsWith("/page-blueprints")) {
        return Promise.resolve({ items: [] });
      }
      return Promise.resolve({ items: [] });
    });
    const { rerender } = render(<BlueprintSettingsPanel projectId="project-1" />);
    fireEvent.change(await screen.findByLabelText("Blueprintnaam"), {
      target: { value: "Dienstpagina" },
    });
    fireEvent.change(screen.getByLabelText("Referentiepagina"), {
      target: { value: "page-19" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Blueprint maken" }));

    rerender(<BlueprintSettingsPanel projectId="project-2" />);
    finishCreate?.(blueprint);

    await waitFor(() => expect(screen.getByLabelText("Blueprintnaam")).toHaveValue(""));
    expect(screen.queryByText("Hero (algemeen)")).not.toBeInTheDocument();
  });

  it("shows a register error without exposing the legacy empty state", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/page-blueprints")) return Promise.reject(new Error("Register offline"));
      return Promise.resolve({ items: [] });
    });

    render(<BlueprintSettingsPanel projectId="project-1" />);

    expect(await screen.findByRole("status")).toHaveTextContent("Register offline");
    expect(screen.getByText("Blueprintregister kon niet worden geladen.")).toBeVisible();
    expect(screen.queryByText(/oude paginapakket/)).not.toBeInTheDocument();
    expect(screen.queryByText("Blueprintregister laden...")).not.toBeInTheDocument();
  });

  it("marks the selected registry item accessibly", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/page-blueprints")) return Promise.resolve({ items: [blueprint] });
      return Promise.resolve({ items: [] });
    });

    render(<BlueprintSettingsPanel projectId="project-1" />);

    expect(await screen.findByRole("button", { name: /Dienstpagina/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("shows a non-destructive legacy migration candidate", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/page-blueprints")) {
        return Promise.resolve({
          items: [],
          legacy_candidates: [{
            source_wordpress_page_id: "page-19",
            builder: "acf",
            seo_plugin: "yoast",
            state: "capture_required",
          }],
        });
      }
      return Promise.resolve({ items: [] });
    });

    render(<BlueprintSettingsPanel projectId="project-1" />);

    expect(await screen.findByText(/Geldige oude paginapakketinstellingen gevonden/)).toBeVisible();
    expect(screen.getByText(/oude instellingen blijven behouden/)).toBeVisible();
  });

  it("locks destructive actions while semantic roles are being saved", async () => {
    let finishSave: ((value: typeof blueprint) => void) | undefined;
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (!init && path.endsWith("/page-blueprints")) return Promise.resolve({ items: [blueprint] });
      if (!init && path.endsWith("/wordpress-pages")) return Promise.resolve({ items: [] });
      if (init?.method === "PUT") {
        return new Promise((resolve) => { finishSave = resolve; });
      }
      return Promise.resolve(blueprint);
    });
    render(<BlueprintSettingsPanel projectId="project-1" />);
    fireEvent.click(await screen.findByRole("button", { name: /Hero \(algemeen\)/ }));
    fireEvent.change(screen.getByLabelText("Rol voor Hero (algemeen)"), {
      target: { value: "introduction" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Rollen opslaan" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Verwijderen" })).toBeDisabled());
    finishSave?.(blueprint);
    await waitFor(() => expect(screen.getByRole("button", { name: "Verwijderen" })).toBeEnabled());
  });
});

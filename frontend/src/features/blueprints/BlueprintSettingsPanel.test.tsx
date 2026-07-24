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
  wordpress_snapshot_id: 901,
  snapshot_version: 2,
  schema_version: "snapshot-text-v1",
  adapter_version: "acf-v1",
  capture_state: "ready",
  migration_state: "native",
  verified_at: "2026-07-24T10:30:00Z",
  created_at: "2026-07-23T09:15:00Z",
  builder: "acf",
  seo_plugin: "yoast",
  version: 1,
  structure_hash: "hash-v1",
  state: "ready",
  is_default_for_page_type: false,
  supersedes_id: null,
  content_schema: {
    schema_version: "snapshot-text-v1",
    document_fields: [
      {
        id: "document:title",
        path: "post_title",
        label: "Paginatitel",
        value_type: "heading",
        current_value: "Transmissie revisie",
        required: true,
        max_length: 180,
      },
      {
        id: "document:slug",
        path: "post_name",
        label: "Slug",
        value_type: "plain_text",
        current_value: "transmissie-revisie",
        required: true,
        max_length: 160,
      },
      {
        id: "seo:title",
        path: "seo.title",
        label: "SEO-titel",
        value_type: "seo_title",
        current_value: "",
        required: true,
        max_length: 70,
      },
      {
        id: "seo:meta_description",
        path: "seo.meta_description",
        label: "Meta description",
        value_type: "meta_description",
        current_value: "",
        required: true,
        max_length: 170,
      },
      {
        id: "seo:focus_keyword",
        path: "seo.focus_keyword",
        label: "Focuszoekwoord",
        value_type: "focus_keyword",
        current_value: "",
        required: true,
        max_length: 160,
      },
    ],
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

    fireEvent.change(await screen.findByLabelText("Templatenaam"), {
      target: { value: "Dienstpagina" },
    });
    fireEvent.change(screen.getByLabelText("Paginatype"), {
      target: { value: "service" },
    });
    fireEvent.change(screen.getByLabelText("Bronpagina"), {
      target: { value: "page-19" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Template opnemen" }));

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

  it("shows immutable snapshot identity instead of a mutable blueprint page", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/page-blueprints")) {
        return Promise.resolve({ items: [blueprint] });
      }
      return Promise.resolve({ items: [] });
    });

    render(<BlueprintSettingsPanel projectId="project-1" />);

    expect(await screen.findByText("Snapshotversie 2")).toBeVisible();
    expect(screen.getByText("Verborgen WordPress-template")).toBeVisible();
    expect(screen.getByText("Adapter acf-v1")).toBeVisible();
    expect(screen.getByText("Schema snapshot-text-v1")).toBeVisible();
    expect(screen.getByText("7 tekstvelden")).toBeVisible();
    expect(screen.getByText(/Laatst gecontroleerd/)).toBeVisible();
    expect(screen.queryByText("Blueprintpagina")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Verwijderen" })).not.toBeInTheDocument();
  });

  it("migrates existing templates and keeps per-item recovery visible", async () => {
    const legacyItems = Array.from({ length: 7 }, (_, index) => ({
      ...blueprint,
      id: `legacy-${index + 1}`,
      name: `Template ${index + 1}`,
      wordpress_snapshot_id: null,
      snapshot_version: null,
      schema_version: null,
      adapter_version: null,
      capture_state: null,
      migration_state: "legacy",
      verified_at: null,
    }));
    let registryReads = 0;
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (!init && path.endsWith("/page-blueprints")) {
        registryReads += 1;
        return Promise.resolve({
          items: registryReads === 1
            ? legacyItems
            : [
                ...legacyItems,
                ...[...legacyItems.slice(0, 4), legacyItems[6]].map((item, index) => ({
                  ...blueprint,
                  id: `snapshot-${index + 1}`,
                  name: item.name,
                  supersedes_id: item.id,
                })),
              ],
        });
      }
      if (!init && path.endsWith("/wordpress-pages")) {
        return Promise.resolve({ items: [] });
      }
      if (init?.method === "POST" && path.includes("/page-blueprints/migrate")) {
        if (path.includes("?blueprint_id=")) {
          return Promise.resolve({
            items: [{
              blueprint_id: legacyItems[4].id,
              state: "failed",
              action: "recapture",
            }],
          });
        }
        return Promise.resolve({
          items: [
            ...legacyItems.slice(0, 4).map((item) => ({
              blueprint_id: item.id,
              state: "migrated",
            })),
            {
              blueprint_id: legacyItems[4].id,
              state: "failed",
              action: "recapture",
            },
            {
              blueprint_id: legacyItems[5].id,
              state: "pending",
              action: "wait",
            },
            {
              blueprint_id: legacyItems[6].id,
              state: "incompatible",
              action: "new_proposal",
            },
          ],
        });
      }
      return Promise.resolve(blueprint);
    });

    render(<BlueprintSettingsPanel projectId="project-1" />);
    fireEvent.click(await screen.findByRole("button", {
      name: "Bestaande templates omzetten",
    }));

    expect(await screen.findByText("4 templates omgezet")).toBeVisible();
    expect(screen.getByText("1 template opnieuw opnemen")).toBeVisible();
    expect(screen.getByRole("button", {
      name: "Opnieuw opnemen: Template 5",
    })).toBeVisible();
    expect(screen.getByText("1 template wacht op een actieve generatie")).toBeVisible();
    expect(screen.getByText("Nieuw voorstel nodig: Template 7")).toBeVisible();

    fireEvent.click(screen.getByRole("button", {
      name: "Opnieuw opnemen: Template 5",
    }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/projects/project-1/page-blueprints/migrate?blueprint_id=legacy-5",
      { method: "POST" },
    ));
    expect(screen.getByText("1 template wacht op een actieve generatie")).toBeVisible();
    expect(screen.getByText("Nieuw voorstel nodig: Template 7")).toBeVisible();
  });

  it("restores persisted migration recovery after reload", async () => {
    const waiting = {
      ...blueprint,
      id: "legacy-waiting",
      name: "Wachtend template",
      wordpress_snapshot_id: null,
    };
    const incompatible = {
      ...blueprint,
      id: "legacy-incompatible",
      name: "Oud template",
      wordpress_snapshot_id: null,
    };
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/page-blueprints")) {
        return Promise.resolve({
          items: [waiting, incompatible],
          migration_results: [
            {
              blueprint_id: waiting.id,
              state: "pending",
              action: "wait",
            },
            {
              blueprint_id: incompatible.id,
              state: "incompatible",
              action: "new_proposal",
            },
          ],
        });
      }
      return Promise.resolve({ items: [] });
    });

    render(<BlueprintSettingsPanel projectId="project-1" />);

    expect(await screen.findByText("1 template wacht op een actieve generatie")).toBeVisible();
    expect(screen.getByText("Nieuw voorstel nodig: Oud template")).toBeVisible();
  });

  it("hides migration after every legacy template has a successor", async () => {
    const legacy = {
      ...blueprint,
      id: "legacy-1",
      wordpress_snapshot_id: null,
      snapshot_version: null,
      schema_version: null,
      adapter_version: null,
      capture_state: null,
      migration_state: null,
      verified_at: null,
    };
    const successor = {
      ...blueprint,
      id: "snapshot-1",
      supersedes_id: legacy.id,
    };
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/page-blueprints")) {
        return Promise.resolve({ items: [legacy, successor] });
      }
      return Promise.resolve({ items: [] });
    });

    render(<BlueprintSettingsPanel projectId="project-1" />);

    expect(await screen.findAllByRole("button", { name: /Dienstpagina/ })).toHaveLength(2);
    expect(screen.queryByRole("button", {
      name: "Bestaande templates omzetten",
    })).not.toBeInTheDocument();
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
      if (init?.method === "POST" && path.endsWith("/verify")) {
        return Promise.reject(new Error("Blueprint structure has changed"));
      }
      if (!init && path.endsWith("/page-blueprints/blueprint-1")) {
        return Promise.resolve(stale);
      }
      return Promise.resolve(blueprint);
    });

    render(<BlueprintSettingsPanel projectId="project-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Controleren" }));

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
    fireEvent.change(await screen.findByLabelText("Templatenaam"), {
      target: { value: "Dienstpagina" },
    });
    fireEvent.change(screen.getByLabelText("Bronpagina"), {
      target: { value: "page-19" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Template opnemen" }));

    rerender(<BlueprintSettingsPanel projectId="project-2" />);
    finishCreate?.(blueprint);

    await waitFor(() => expect(screen.getByLabelText("Templatenaam")).toHaveValue(""));
    expect(screen.queryByText("Hero (algemeen)")).not.toBeInTheDocument();
  });

  it("shows a register error without exposing the legacy empty state", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/page-blueprints")) return Promise.reject(new Error("Register offline"));
      return Promise.resolve({ items: [] });
    });

    render(<BlueprintSettingsPanel projectId="project-1" />);

    expect(await screen.findByRole("status")).toHaveTextContent("Register offline");
    expect(screen.getByText("Templateregister kon niet worden geladen.")).toBeVisible();
    expect(screen.queryByText(/oude paginapakket/)).not.toBeInTheDocument();
    expect(screen.queryByText("Templateregister laden...")).not.toBeInTheDocument();
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
    expect(screen.queryByRole("button", {
      name: "Bestaande templates omzetten",
    })).not.toBeInTheDocument();
  });

  it("locks snapshot actions while semantic roles are being saved", async () => {
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

    await waitFor(() => expect(screen.getByRole("button", { name: "Controleren" })).toBeDisabled());
    finishSave?.(blueprint);
    await waitFor(() => expect(screen.getByRole("button", { name: "Controleren" })).toBeEnabled());
  });
});

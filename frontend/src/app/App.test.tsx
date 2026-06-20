import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { apiRequest } from "../lib/api";
import { supabase } from "../lib/supabase";

vi.mock("../lib/api", () => ({
  apiRequest: vi.fn(),
}));

vi.mock("../lib/supabase", () => ({
  supabase: {
    auth: {
      signOut: vi.fn(),
    },
  },
}));

describe("App", () => {
  beforeEach(() => {
    vi.mocked(apiRequest).mockReset();
    vi.mocked(supabase!.auth.signOut).mockReset();
    window.location.hash = "";
  });

  it("renders the product name and loads live projects", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce({ items: [] });

    render(<App />);

    expect(screen.getByRole("link", { name: "WP FixPilot home" })).toBeVisible();
    expect(await screen.findByRole("heading", {
      name: "Maak je eerste project aan",
    })).toBeVisible();
    expect(apiRequest).toHaveBeenCalledWith("/projects");
  });

  it("signs out through Supabase", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce({ items: [] });
    vi.mocked(supabase!.auth.signOut).mockResolvedValueOnce({ error: null });

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Uitloggen" }));

    expect(supabase!.auth.signOut).toHaveBeenCalledOnce();
  });

  it("deletes the active project and selects the next project", async () => {
    vi.mocked(apiRequest)
      .mockResolvedValueOnce({
        items: [
          {
            id: "project-1",
            organization_id: "org-1",
            name: "SHM Transmissie",
            domain: "https://shmtransmissie.nl",
          },
          {
            id: "project-2",
            organization_id: "org-1",
            name: "Tweede Site",
            domain: "https://tweede.example",
          },
        ],
      })
      .mockResolvedValueOnce(undefined);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Project wijzigen" }));
    fireEvent.click(screen.getByRole("button", { name: "Project verwijderen" }));
    fireEvent.click(screen.getByRole("button", { name: "Ja, verwijderen" }));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith("/projects/project-1", {
        method: "DELETE",
      }),
    );
    expect(await screen.findByText("tweede.example")).toBeVisible();
  });
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SearchConsolePage } from "./SearchConsolePage";

const apiRequest = vi.fn();
const gscData = {
  pages: [
    {
      date: "2026-06-01",
      page_url: "https://shmtransmissie.nl/revisie",
      clicks: 120,
      impressions: 4000,
      ctr: 0.03,
      average_position: 4.2,
    },
  ],
  queries: [
    {
      date: "2026-06-01",
      query: "transmissie revisie specialist",
      page_url: "https://shmtransmissie.nl/revisie",
      clicks: 70,
      impressions: 2100,
      ctr: 0.0333,
      average_position: 3.8,
    },
  ],
};

vi.mock("../../lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

describe("SearchConsolePage", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    sessionStorage.clear();
    apiRequest.mockImplementation((path: string) => {
      if (path === "/projects/shm/search-console-data") {
        return Promise.resolve(gscData);
      }
      if (path === "/projects/shm/sync-search-console") {
        return Promise.resolve({ imported_pages: 1, imported_queries: 1 });
      }
      if (path === "/google/connections/google-1/search-console-properties") {
        return Promise.resolve({
          items: [
            {
              siteUrl: "sc-domain:shmtransmissie.nl",
              permissionLevel: "siteOwner",
            },
          ],
        });
      }
      if (path === "/projects/shm/connect-search-console") {
        return Promise.resolve({ status: "connected" });
      }
      return Promise.reject(new Error(`Unexpected path ${path}`));
    });
  });

  it("loads Search Console data for the active project", async () => {
    render(<SearchConsolePage projectId="shm" />);

    expect((await screen.findAllByText("120")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("4.000").length).toBeGreaterThan(0);
    expect(screen.getByText("transmissie revisie specialist")).toBeVisible();
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/shm/search-console-data",
      ),
    );
  });

  it("syncs Search Console data through the project API", async () => {
    render(<SearchConsolePage projectId="shm" />);
    await screen.findAllByText("120");

    fireEvent.click(screen.getByRole("button", { name: "Data synchroniseren" }));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/shm/sync-search-console",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("binds a selected Search Console property after Google OAuth", async () => {
    sessionStorage.setItem("wpfixpilot.googleConnectionId", "google-1");
    render(<SearchConsolePage projectId="shm" />);

    expect(
      await screen.findByLabelText("Search Console property"),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Property koppelen" }));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/shm/connect-search-console",
        expect.objectContaining({
          body: JSON.stringify({
            google_connection_id: "google-1",
            permission_level: "siteOwner",
            property_uri: "sc-domain:shmtransmissie.nl",
          }),
          method: "POST",
        }),
      ),
    );
  });
});

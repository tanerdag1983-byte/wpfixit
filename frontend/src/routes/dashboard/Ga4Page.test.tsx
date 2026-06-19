import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Ga4Page } from "./Ga4Page";

const apiRequest = vi.fn();
const ga4Data = {
  pages: [
    {
      date: "2026-06-01",
      page_path: "/revisie",
      sessions: 840,
      users: 610,
      engagement_rate: 0.68,
      conversions: 42,
      revenue: 1250,
    },
  ],
  traffic_sources: [
    {
      date: "2026-06-01",
      source: "google",
      medium: "organic",
      campaign: null,
      sessions: 620,
      users: 455,
      engagement_rate: 0.71,
      conversions: 36,
      revenue: 900,
    },
  ],
};

vi.mock("../../lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

describe("Ga4Page", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    sessionStorage.clear();
    apiRequest.mockImplementation((path: string) => {
      if (path === "/projects/shm/ga4-data") {
        return Promise.resolve(ga4Data);
      }
      if (path === "/projects/shm/sync-ga4") {
        return Promise.resolve({ imported_pages: 1, imported_sources: 1 });
      }
      if (path === "/google/connections/google-1/ga4-properties") {
        return Promise.resolve({
          items: [
            {
              account: "accounts/123",
              account_display_name: "SHM",
              property: "properties/456",
              display_name: "SHM GA4",
            },
          ],
        });
      }
      if (path === "/projects/shm/connect-ga4") {
        return Promise.resolve({ status: "connected" });
      }
      return Promise.reject(new Error(`Unexpected path ${path}`));
    });
  });

  it("loads GA4 data for the active project", async () => {
    render(<Ga4Page projectId="shm" />);

    expect((await screen.findAllByText("840")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("42").length).toBeGreaterThan(0);
    expect(screen.getByText("google / organic")).toBeVisible();
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith("/projects/shm/ga4-data"),
    );
  });

  it("syncs GA4 data through the project API", async () => {
    render(<Ga4Page projectId="shm" />);
    await screen.findAllByText("840");

    fireEvent.click(screen.getByRole("button", { name: "Data synchroniseren" }));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/shm/sync-ga4",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("binds a selected GA4 property after Google OAuth", async () => {
    sessionStorage.setItem("wpfixpilot.googleConnectionId", "google-1");
    render(<Ga4Page projectId="shm" />);

    expect(await screen.findByLabelText("GA4 property")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Property koppelen" }));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/shm/connect-ga4",
        expect.objectContaining({
          body: JSON.stringify({
            account_id: "accounts/123",
            display_name: "SHM GA4",
            google_connection_id: "google-1",
            property_id: "properties/456",
          }),
          method: "POST",
        }),
      ),
    );
  });
});

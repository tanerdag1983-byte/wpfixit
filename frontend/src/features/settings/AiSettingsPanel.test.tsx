import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AiSettingsPanel } from "./AiSettingsPanel";

const apiRequest = vi.fn();

vi.mock("../../lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

describe("AiSettingsPanel", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/wordpress-connection")) {
        return Promise.reject(new Error("not connected"));
      }
      if (path.endsWith("/wordpress-pages")) return Promise.resolve({ count: 0 });
      if (path.endsWith("/ai-connections")) return Promise.resolve({ items: [] });
      if (path.endsWith("/ai-policy")) return Promise.resolve({ configured: false });
      if (path.endsWith("/company-profile")) {
        return Promise.resolve({ configured: false });
      }
      if (path.endsWith("/dataforseo-connection")) {
        return Promise.resolve({ configured: false });
      }
      return Promise.resolve({});
    });
  });

  it("shows connection, project policy and company context settings", async () => {
    render(
      <AiSettingsPanel organizationId="org-1" projectId="project-1" />,
    );

    expect(
      screen.getByRole("heading", { name: "Website koppelen" }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "AI-verbindingen" }),
    ).toBeVisible();
    expect(
      await screen.findByRole("heading", { name: "AI-model voor dit project" }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Bedrijf- en websiteprofiel" }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "DataForSEO" }),
    ).toBeVisible();
  });

  it("does not expose legacy mappings while blueprint availability is loading", () => {
    apiRequest.mockImplementation((path: string) => {
      if (path.endsWith("/page-blueprints")) return new Promise(() => undefined);
      if (path.endsWith("/wordpress-pages")) return Promise.resolve({ items: [] });
      return Promise.resolve({});
    });

    render(<AiSettingsPanel organizationId="org-1" projectId="project-1" />);

    expect(
      screen.queryByRole("heading", { name: "Standaard paginapakket" }),
    ).not.toBeInTheDocument();
  });
});

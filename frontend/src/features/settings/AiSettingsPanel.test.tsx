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
      if (path.endsWith("/ai-connections")) return Promise.resolve({ items: [] });
      if (path.endsWith("/ai-policy")) return Promise.resolve({ configured: false });
      if (path.endsWith("/company-profile")) {
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
      screen.getByRole("heading", { name: "AI-verbindingen" }),
    ).toBeVisible();
    expect(
      await screen.findByRole("heading", { name: "Modelbeleid voor dit project" }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Bedrijf- en websiteprofiel" }),
    ).toBeVisible();
  });
});

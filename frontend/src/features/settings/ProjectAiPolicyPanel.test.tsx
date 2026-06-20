import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectAiPolicyPanel } from "./ProjectAiPolicyPanel";

const apiRequest = vi.fn();

vi.mock("../../lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

describe("ProjectAiPolicyPanel", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest
      .mockResolvedValueOnce({
        items: [
          {
            id: "openai-1",
            name: "OpenAI",
            provider: "openai",
            default_model: "gpt-5.4-mini",
            enabled: true,
          },
          {
            id: "claude-1",
            name: "Claude",
            provider: "anthropic",
            default_model: "claude-sonnet-4-5",
            enabled: true,
          },
        ],
      })
      .mockResolvedValueOnce({
        configured: true,
        primary: {
          connection_id: "openai-1",
          model: "gpt-5.4-mini",
        },
        fallback: {
          connection_id: "claude-1",
          model: "claude-sonnet-4-5",
        },
      });
  });

  it("loads and saves primary and fallback models for one project", async () => {
    apiRequest.mockResolvedValueOnce({ configured: true });
    render(
      <ProjectAiPolicyPanel
        organizationId="org-1"
        projectId="project-1"
      />,
    );

    expect(await screen.findByDisplayValue("gpt-5.4-mini")).toBeVisible();
    expect(screen.getByDisplayValue("claude-sonnet-4-5")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Modelbeleid opslaan" }));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/project-1/ai-policy",
        expect.objectContaining({ method: "PUT" }),
      ),
    );
  });

  it("explains that model selection is project-specific", async () => {
    render(
      <ProjectAiPolicyPanel
        organizationId="org-1"
        projectId="project-1"
      />,
    );

    expect(
      await screen.findByRole("heading", {
        name: "AI-model voor dit project",
      }),
    ).toBeVisible();
    expect(
      screen.getByText(/Deze keuze geldt alleen voor dit project/i),
    ).toBeVisible();
  });
});

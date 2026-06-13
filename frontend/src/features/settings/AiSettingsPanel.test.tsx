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
    apiRequest
      .mockResolvedValueOnce({
        configured: true,
        provider: "openai_compatible",
        base_url: "https://ai.example.com/v1",
        model: "seo-model",
      })
      .mockResolvedValueOnce({
        configured: true,
        company_name: "SHM Transmissie",
        description: "Transmissiespecialist",
        audience: "Autobezitters",
        services: ["Diagnose", "Revisie"],
        tone_of_voice: "Deskundig",
        custom_prompt: "Noem alleen aantoonbare voordelen.",
      });
  });

  it("lets an owner select a model and define company context", () => {
    render(
      <AiSettingsPanel
        organizationId="org-1"
        projectId="project-1"
      />,
    );

    expect(screen.getByLabelText("Model")).toBeVisible();
    expect(screen.getByLabelText("API-key")).toBeVisible();
    expect(screen.getByLabelText("Bedrijfsprofiel prompt")).toBeVisible();
    expect(screen.getByRole("button", { name: "AI-koppeling opslaan" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Verbinding testen" })).toBeVisible();
  });

  it("loads the saved model and company profile", async () => {
    render(
      <AiSettingsPanel
        organizationId="org-1"
        projectId="project-1"
      />,
    );

    expect(await screen.findByDisplayValue("seo-model")).toBeVisible();
    expect(screen.getByDisplayValue("SHM Transmissie")).toBeVisible();
    expect(screen.getByDisplayValue("Diagnose, Revisie")).toBeVisible();
  });
});

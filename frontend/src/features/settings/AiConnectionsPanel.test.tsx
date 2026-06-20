import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AiConnectionsPanel } from "./AiConnectionsPanel";

const apiRequest = vi.fn();

vi.mock("../../lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

describe("AiConnectionsPanel", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValueOnce({
      items: [
        {
          id: "connection-1",
          name: "Claude productie",
          provider: "anthropic",
          base_url: "https://api.anthropic.com/v1",
          default_model: "claude-sonnet-4-5",
          enabled: true,
          configured: true,
          last_test_status: null,
        },
      ],
    });
  });

  it("lists existing connections without exposing credentials", async () => {
    render(<AiConnectionsPanel organizationId="org-1" />);

    expect(await screen.findByText("Claude productie")).toBeVisible();
    expect(screen.getByText("Anthropic")).toBeVisible();
    expect(screen.queryByText(/secret/i)).not.toBeInTheDocument();
  });

  it("creates and tests a provider connection", async () => {
    apiRequest
      .mockResolvedValueOnce({
        id: "connection-2",
        name: "Gemini SEO",
        provider: "gemini",
        base_url: "https://generativelanguage.googleapis.com/v1beta",
        default_model: "gemini-2.5-flash",
        enabled: true,
        configured: true,
      })
      .mockResolvedValueOnce({
        id: "connection-2",
        name: "Gemini SEO",
        provider: "gemini",
        base_url: "https://generativelanguage.googleapis.com/v1beta",
        default_model: "gemini-2.5-flash",
        enabled: true,
        configured: true,
        last_test_status: "connected",
      })
      .mockResolvedValueOnce({ items: [] });
    render(<AiConnectionsPanel organizationId="org-1" />);
    await screen.findByText("Claude productie");

    fireEvent.change(screen.getByLabelText("Naam verbinding"), {
      target: { value: "Gemini SEO" },
    });
    fireEvent.change(screen.getByLabelText("Provider"), {
      target: { value: "gemini" },
    });
    fireEvent.change(screen.getByLabelText("Standaardmodel"), {
      target: { value: "gemini-2.5-flash" },
    });
    fireEvent.change(screen.getByLabelText("API-key"), {
      target: { value: "private-key" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verbinding toevoegen" }));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/organizations/org-1/ai-connections",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Gemini SEO testen" }),
    );
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/organizations/org-1/ai-connections/connection-2/test",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("offers OpenRouter as its own provider with OpenRouter defaults", async () => {
    render(<AiConnectionsPanel organizationId="org-1" />);
    await screen.findByText("Claude productie");

    fireEvent.change(screen.getByLabelText("Provider"), {
      target: { value: "openrouter" },
    });

    expect(screen.getByRole("option", { name: "OpenRouter" })).toBeVisible();
    expect(screen.getByLabelText("API base URL")).toHaveValue(
      "https://openrouter.ai/api/v1",
    );
    expect(screen.getByLabelText("Standaardmodel")).toHaveValue(
      "openai/gpt-4o-mini",
    );
  });

  it("reloads and shows the stored provider message after a failed test", async () => {
    apiRequest
      .mockRejectedValueOnce(
        new Error("AI provider connection failed: insufficient quota"),
      )
      .mockResolvedValueOnce({
        items: [
          {
            id: "connection-1",
            name: "Claude productie",
            provider: "anthropic",
            base_url: "https://api.anthropic.com/v1",
            default_model: "claude-sonnet-4-5",
            enabled: true,
            configured: true,
            last_test_status: "failed",
            last_test_message:
              "AI provider connection failed: insufficient quota",
          },
        ],
      });
    render(<AiConnectionsPanel organizationId="org-1" />);
    await screen.findByText("Claude productie");

    fireEvent.click(
      screen.getByRole("button", { name: "Claude productie testen" }),
    );

    expect(
      await screen.findByText(
        "AI provider connection failed: insufficient quota",
      ),
    ).toBeVisible();
    expect(
      await screen.findByText(
        "Laatste test: AI provider connection failed: insufficient quota",
      ),
    ).toBeVisible();
    expect(screen.getByText("Mislukt")).toBeVisible();
  });

  it("updates a connection without resending the stored API key", async () => {
    apiRequest.mockResolvedValueOnce({
      id: "connection-1",
      name: "Claude fallback",
      provider: "anthropic",
      base_url: "https://api.anthropic.com/v1",
      default_model: "claude-opus-4-1",
      enabled: true,
      configured: true,
    });
    render(<AiConnectionsPanel organizationId="org-1" />);
    await screen.findByText("Claude productie");

    fireEvent.click(
      screen.getByRole("button", { name: "Claude productie bewerken" }),
    );
    fireEvent.change(screen.getByLabelText("Naam verbinding"), {
      target: { value: "Claude fallback" },
    });
    fireEvent.change(screen.getByLabelText("Standaardmodel"), {
      target: { value: "claude-opus-4-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Wijzigingen opslaan" }));

    await waitFor(() => {
      const [, init] = apiRequest.mock.calls.find(
        ([path]) =>
          path === "/organizations/org-1/ai-connections/connection-1",
      ) as [string, RequestInit];
      expect(init.method).toBe("PUT");
      expect(JSON.parse(init.body as string)).not.toHaveProperty("api_key");
    });
  });
});

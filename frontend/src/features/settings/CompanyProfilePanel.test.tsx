import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CompanyProfilePanel } from "./CompanyProfilePanel";

const apiRequest = vi.fn();

vi.mock("../../lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

describe("CompanyProfilePanel", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValueOnce({
      configured: true,
      company_name: "SHM Transmissie",
      description: "Transmissiespecialist",
      audience: "Autobezitters",
      services: ["Diagnose", "Revisie"],
      tone_of_voice: "Deskundig",
      custom_prompt: "Gebruik alleen aantoonbare voordelen.",
    });
  });

  it("loads and saves a project-specific company prompt", async () => {
    apiRequest.mockResolvedValueOnce({ configured: true });
    render(<CompanyProfilePanel projectId="project-1" />);

    expect(await screen.findByDisplayValue("SHM Transmissie")).toBeVisible();
    const prompt = screen.getByLabelText(/Projectprompt voor dit project/i);
    fireEvent.change(prompt, {
      target: { value: "Schrijf concreet en verwijs naar bewijs." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Profiel opslaan" }));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/project-1/company-profile",
        expect.objectContaining({
          method: "PUT",
          body: expect.stringContaining("Schrijf concreet"),
        }),
      ),
    );
  });

  it("allows saving a project prompt before the company name is filled", async () => {
    apiRequest.mockReset();
    apiRequest
      .mockResolvedValueOnce({ configured: false })
      .mockResolvedValueOnce({
        configured: true,
        company_name: "Website",
        custom_prompt: "Gebruik mijn projectprompt.",
      });

    render(<CompanyProfilePanel projectId="project-1" />);

    const prompt = await screen.findByLabelText(/Projectprompt voor dit project/i);
    fireEvent.change(prompt, {
      target: { value: "Gebruik mijn projectprompt." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Profiel opslaan" }));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/project-1/company-profile",
        expect.objectContaining({
          method: "PUT",
          body: expect.stringContaining('"company_name":"Website"'),
        }),
      ),
    );
  });

  it("labels the company profile prompt as project-specific", async () => {
    render(<CompanyProfilePanel projectId="project-1" />);

    expect(
      await screen.findByText(/Projectprompt voor dit project/i),
    ).toBeVisible();
    expect(
      screen.getByText(/Deze prompt wordt alleen gebruikt voor dit project/i),
    ).toBeVisible();
  });
});

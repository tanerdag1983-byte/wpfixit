import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DataForSeoPanel } from "./DataForSeoPanel";

const apiRequest = vi.fn();

vi.mock("../../lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

describe("DataForSeoPanel", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (!init) {
        return Promise.resolve({
          configured: true,
          login: "account@example.com",
          enabled: true,
          last_test_status: null,
          last_test_message: null,
        });
      }
      if (path.endsWith("/test")) {
        return Promise.resolve({
          configured: true,
          login: "account@example.com",
          enabled: true,
          last_test_status: "connected",
          last_test_message: "Connection successful",
        });
      }
      return Promise.resolve({
        configured: true,
        login: "account@example.com",
        enabled: true,
        last_test_status: null,
        last_test_message: null,
      });
    });
  });

  it("loads and tests the organization connection", async () => {
    render(<DataForSeoPanel organizationId="org-1" />);

    expect(
      await screen.findByDisplayValue("account@example.com"),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Verbinding testen" }));

    expect(
      await screen.findByText("DataForSEO-verbinding is bereikbaar."),
    ).toBeVisible();
    expect(apiRequest).toHaveBeenCalledWith(
      "/organizations/org-1/dataforseo-connection/test",
      { method: "POST" },
    );
  });

  it("saves credentials without displaying the password again", async () => {
    apiRequest.mockImplementationOnce(() =>
      Promise.resolve({
        configured: false,
        login: null,
        enabled: false,
        last_test_status: null,
        last_test_message: null,
      }),
    );
    render(<DataForSeoPanel organizationId="org-1" />);

    fireEvent.change(await screen.findByLabelText("DataForSEO login"), {
      target: { value: "account@example.com" },
    });
    fireEvent.change(screen.getByLabelText("DataForSEO wachtwoord"), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verbinding opslaan" }));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/organizations/org-1/dataforseo-connection",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({
            login: "account@example.com",
            password: "secret",
            enabled: true,
          }),
        }),
      ),
    );
    expect(
      await screen.findByText("DataForSEO-verbinding is opgeslagen."),
    ).toBeVisible();
    expect(screen.getByLabelText("DataForSEO wachtwoord")).toHaveValue("");
  });

  it("explains that the generated API password is required", async () => {
    render(<DataForSeoPanel organizationId="org-1" />);

    const password = await screen.findByLabelText("DataForSEO wachtwoord");
    const explanation = screen.getByText(
      /automatisch gegenereerde DataForSEO API-wachtwoord/i,
    );
    expect(explanation).toBeVisible();
    expect(password).toHaveAttribute("aria-describedby", explanation.id);
    expect(
      screen.getByRole("link", { name: "API-wachtwoord bekijken" }),
    ).toHaveAttribute("href", "https://app.dataforseo.com/api-access");
  });
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WordPressBridgePanel } from "./WordPressBridgePanel";

const apiRequest = vi.fn();

vi.mock("../../lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

describe("WordPressBridgePanel", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.endsWith("/wordpress-connection")) {
        return Promise.reject(new Error("not connected"));
      }
      if (path.endsWith("/wordpress-pages")) return Promise.resolve({ count: 0 });
      if (path.endsWith("/wordpress-connect") && init?.method === "POST") {
        return Promise.resolve({
          project_id: "project-1",
          site_url: "https://example.com",
          plugin_version: "0.1.0",
          seo_plugin: "yoast",
          health_state: "connected",
        });
      }
      if (path.endsWith("/audit") && init?.method === "POST") {
        return Promise.resolve({ audited_count: 89 });
      }
      return Promise.resolve({});
    });
  });

  it("connects WordPress with site URL and bridge secret", async () => {
    render(<WordPressBridgePanel projectId="project-1" />);

    fireEvent.change(screen.getByLabelText("WordPress URL"), {
      target: { value: "https://example.com" },
    });
    fireEvent.change(screen.getByLabelText("Bridge secret"), {
      target: { value: "a".repeat(64) },
    });
    fireEvent.click(screen.getByRole("button", { name: "WordPress koppelen" }));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/project-1/wordpress-connect",
        {
          method: "POST",
          body: JSON.stringify({
            site_url: "https://example.com",
            secret: "a".repeat(64),
          }),
        },
      ),
    );
    expect(await screen.findByText("WordPress bridge is verbonden.")).toBeVisible();
  });

  it("runs a WordPress audit after a connection exists", async () => {
    apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.endsWith("/wordpress-connection")) {
        return Promise.resolve({
          project_id: "project-1",
          site_url: "https://example.com",
          plugin_version: "0.1.0",
          seo_plugin: "yoast",
          health_state: "connected",
        });
      }
      if (path.endsWith("/wordpress-pages")) return Promise.resolve({ count: 89 });
      if (path.endsWith("/audit") && init?.method === "POST") {
        return Promise.resolve({ audited_count: 89 });
      }
      return Promise.resolve({});
    });

    render(<WordPressBridgePanel projectId="project-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "SEO-audit draaien" }));

    expect(await screen.findByText("89 WordPress-pagina's geaudit.")).toBeVisible();
  });
});

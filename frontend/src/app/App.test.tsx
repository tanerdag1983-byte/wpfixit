import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { apiRequest } from "../lib/api";

vi.mock("../lib/api", () => ({
  apiRequest: vi.fn(),
}));

describe("App", () => {
  it("renders the product name and loads live projects", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce({ items: [] });

    render(<App />);

    expect(screen.getByRole("link", { name: "WP FixPilot home" })).toBeVisible();
    expect(await screen.findByRole("heading", {
      name: "Maak je eerste project aan",
    })).toBeVisible();
    expect(apiRequest).toHaveBeenCalledWith("/projects");
  });
});

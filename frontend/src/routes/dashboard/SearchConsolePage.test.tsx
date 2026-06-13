import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SearchConsolePage } from "./SearchConsolePage";

describe("SearchConsolePage", () => {
  it("shows Search Console metrics and top queries", () => {
    render(<SearchConsolePage />);

    expect(
      screen.getByRole("heading", { name: "Search Console" }),
    ).toBeVisible();
    expect(screen.getByText("transmissie revisie")).toBeVisible();
    expect(screen.getByText("12.4K")).toBeVisible();
  });
});

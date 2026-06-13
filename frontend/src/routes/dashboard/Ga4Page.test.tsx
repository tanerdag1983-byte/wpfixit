import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Ga4Page } from "./Ga4Page";

describe("Ga4Page", () => {
  it("shows traffic and conversion metrics", () => {
    render(<Ga4Page />);

    expect(
      screen.getByRole("heading", { name: "Google Analytics 4" }),
    ).toBeVisible();
    expect(screen.getByText("12.1K")).toBeVisible();
    expect(screen.getByText("google / organic")).toBeVisible();
  });
});

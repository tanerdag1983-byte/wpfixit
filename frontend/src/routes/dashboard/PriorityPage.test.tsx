import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PriorityPage } from "./PriorityPage";

describe("PriorityPage", () => {
  it("shows the combined page score and source metrics", () => {
    render(<PriorityPage />);

    expect(screen.getByRole("heading", { name: "SEO-prioriteiten" })).toBeVisible();
    expect(screen.getByText("94")).toBeVisible();
    expect(screen.getByText(/1,2% CTR/)).toBeVisible();
    expect(screen.getByText(/1\.840 sessies/)).toBeVisible();
  });
});

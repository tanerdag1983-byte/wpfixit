import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OpportunitiesPage } from "./OpportunitiesPage";

describe("OpportunitiesPage", () => {
  it("shows evidence-backed opportunities", () => {
    render(<OpportunitiesPage />);

    expect(screen.getByRole("heading", { name: "Kansen" })).toBeVisible();
    expect(screen.getByText(/12\.400 impressies/)).toBeVisible();
    expect(screen.getAllByText("Voorstel")).toHaveLength(3);
  });
});

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PublishingReview } from "./PublishingReview";

describe("PublishingReview", () => {
  it("shows an exact diff and requires approval before publishing", () => {
    render(<PublishingReview />);

    expect(
      screen.getByRole("heading", { name: "Wijziging beoordelen" }),
    ).toBeVisible();
    expect(screen.getByText("Oude title")).toBeVisible();
    expect(screen.getByText("Nieuwe title")).toBeVisible();
    expect(screen.getByRole("button", { name: "Publiceren" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Goedkeuren" }));

    expect(screen.getByRole("button", { name: "Publiceren" })).toBeEnabled();
  });

  it("requires confirmation before rollback", () => {
    render(<PublishingReview initialState="published" />);

    fireEvent.click(screen.getByRole("button", { name: "Rollback" }));

    expect(screen.getByText("Rollback bevestigen")).toBeVisible();
  });
});

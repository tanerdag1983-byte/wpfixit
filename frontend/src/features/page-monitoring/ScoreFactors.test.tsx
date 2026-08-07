import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScoreFactors } from "./ScoreFactors";

describe("ScoreFactors", () => {
  it("compares current and projected factors with readable labels", () => {
    render(
      <ScoreFactors
        current={{
          overall_score: 61,
          factors: [{
            key: "meta_description",
            value: "",
            points: 0,
            max_points: 10,
            explanation: "Meta description needs attention.",
            suggested_action: "Add a meta description.",
            evidence: { value: "" },
          }],
        }}
        projected={{
          overall_score: 78,
          factors: [{
            key: "meta_description",
            value: "Sterke omschrijving",
            points: 10,
            max_points: 10,
            explanation: "Meta description is present.",
            suggested_action: "",
            evidence: { value: "Sterke omschrijving" },
          }],
        }}
      />,
    );

    expect(screen.getByText("Huidige score 61")).toBeVisible();
    expect(screen.getByText("Verwachte score 78")).toBeVisible();
    expect(
      screen.getByRole("row", { name: /Meta description.*0 van 10.*10 van 10/ }),
    ).toBeVisible();
    expect(screen.getByText("Meta description needs attention.")).toBeVisible();
    expect(screen.getByText("Meta description is present.")).toBeVisible();
  });
});

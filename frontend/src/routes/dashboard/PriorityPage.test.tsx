import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiRequest } from "../../lib/api";
import { PriorityPage } from "./PriorityPage";

vi.mock("../../lib/api", () => ({
  apiRequest: vi.fn(),
}));

describe("PriorityPage", () => {
  beforeEach(() => {
    vi.mocked(apiRequest).mockResolvedValue({
      items: [
        {
          url: "/revisie",
          title: "Transmissie revisie",
          seo_score: 48,
          clicks: 149,
          impressions: 12400,
          ctr: 0.012,
          average_position: 8.2,
          sessions: 1840,
          conversions: 11,
          trend: "-22%",
          priority_score: 94,
          confidence: 0.9,
          components: {},
          action: "Verbeter snippet en herstel conversieverlies",
          evidence: [],
        },
      ],
    });
  });

  it("shows the combined page score and source metrics", async () => {
    render(<PriorityPage projectId="project-1" />);

    expect(
      await screen.findByRole("heading", { name: "SEO-prioriteiten" }),
    ).toBeVisible();
    expect(apiRequest).toHaveBeenCalledWith(
      "/projects/project-1/seo-priority-score?minimum_score=0&limit=100",
    );
    expect(await screen.findByText("94")).toBeVisible();
    expect(screen.getByText(/1,2% CTR/)).toBeVisible();
    expect(screen.getByText(/1\.840 sessies/)).toBeVisible();
  });
});

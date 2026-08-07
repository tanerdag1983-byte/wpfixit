import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PageTimeline } from "./PageTimeline";

describe("PageTimeline", () => {
  it("shows status, checks, and events newest first", () => {
    const onCheck = vi.fn();
    render(
      <PageTimeline
        checking={false}
        events={[
          { id: "old", event_type: "version_observed", payload: {}, created_at: "2026-08-01T08:00:00Z" },
          { id: "new", event_type: "score_created", payload: { overall_score: 61 }, created_at: "2026-08-07T08:00:00Z" },
        ]}
        latestSyncAt="2026-08-07T08:00:00Z"
        nextCheckAt="2026-08-14T08:00:00Z"
        onCheck={onCheck}
        recommendations={[
          {
            id: "recommendation-1",
            page_version_id: "version-1",
            state: "open",
            evidence: {},
            suggested_action: "Voeg een meta description toe.",
            created_at: "2026-08-07T08:00:00Z",
          },
        ]}
        scores={[
          {
            id: "score-2",
            page_version_id: "version-2",
            overall_score: 72,
            factors: [],
            created_at: "2026-08-07T08:00:00Z",
          },
          {
            id: "score-1",
            page_version_id: "version-1",
            overall_score: 61,
            factors: [],
            created_at: "2026-08-01T08:00:00Z",
          },
        ]}
        status="needs_attention"
        capturedVersionId="version-1"
      />,
    );

    expect(screen.getByText("Laatste controle")).toBeVisible();
    expect(screen.getByText("Volgende controle")).toBeVisible();
    const events = screen.getAllByRole("listitem");
    expect(events[0]).toHaveTextContent("Score berekend");
    expect(events[1]).toHaveTextContent("Nieuwe paginaversie gezien");
    expect(screen.getByRole("heading", { name: "Scoreverloop" })).toBeVisible();
    expect(screen.getByRole("row", { name: /72.*version-2/i })).toBeVisible();
    expect(screen.getByRole("row", { name: /61.*Vastgelegde bron/i })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Open suggesties" })).toBeVisible();
    expect(screen.getByText("Voeg een meta description toe.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Nu controleren" }));
    expect(onCheck).toHaveBeenCalledOnce();
  });
});

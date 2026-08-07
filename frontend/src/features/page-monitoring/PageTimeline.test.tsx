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
        status="needs_attention"
      />,
    );

    expect(screen.getByText("Laatste controle")).toBeVisible();
    expect(screen.getByText("Volgende controle")).toBeVisible();
    const events = screen.getAllByRole("listitem");
    expect(events[0]).toHaveTextContent("Score berekend");
    expect(events[1]).toHaveTextContent("Nieuwe paginaversie gezien");
    fireEvent.click(screen.getByRole("button", { name: "Nu controleren" }));
    expect(onCheck).toHaveBeenCalledOnce();
  });
});

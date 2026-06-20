import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PublishingReview } from "./PublishingReview";

const apiRequest = vi.fn();

vi.mock("../../lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

const proposal = {
  id: "proposal-1",
  url: "https://shmtransmissie.nl/revisie",
  change_type: "seo_title",
  before_value: "Oude title",
  after_value: "Nieuwe title",
  approval_state: "proposed",
  created_at: "2026-06-14T10:00:00Z",
};

describe("PublishingReview", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValueOnce({ items: [proposal] });
  });

  it("edits, approves and publishes through the API", async () => {
    apiRequest
      .mockResolvedValueOnce({
        ...proposal,
        after_value: "Beste transmissie revisie",
      })
      .mockResolvedValueOnce({
        ...proposal,
        after_value: "Beste transmissie revisie",
        approval_state: "approved",
      })
      .mockResolvedValueOnce({
        proposal: {
          ...proposal,
          after_value: "Beste transmissie revisie",
          approval_state: "published",
        },
      });
    render(<PublishingReview projectId="shm" />);

    const editor = await screen.findByLabelText("Voorgestelde waarde");
    fireEvent.change(editor, {
      target: { value: "Beste transmissie revisie" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Wijziging opslaan" }));
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/shm/change-proposals/proposal-1",
        expect.objectContaining({ method: "PUT" }),
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "Goedkeuren" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Publiceren" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Publiceren" }));
    expect(await screen.findByText("Gepubliceerd")).toBeVisible();
  });

  it("refreshes a conflicted proposal from WordPress", async () => {
    apiRequest.mockReset();
    apiRequest
      .mockResolvedValueOnce({
        items: [{ ...proposal, approval_state: "conflict" }],
      })
      .mockResolvedValueOnce({
        ...proposal,
        before_value: "Actuele WordPress title",
        approval_state: "proposed",
      });

    render(<PublishingReview projectId="shm" />);

    fireEvent.click(await screen.findByText("Voorstel vernieuwen"));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/shm/change-proposals/proposal-1/refresh",
        { method: "POST" },
      ),
    );
    expect(await screen.findByText("Actuele WordPress title")).toBeVisible();
  });
});

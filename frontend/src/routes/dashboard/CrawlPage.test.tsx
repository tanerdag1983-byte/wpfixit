import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CrawlPage } from "./CrawlPage";

const apiRequest = vi.fn();

vi.mock("../../lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

const run = {
  id: "crawl-1",
  root_url: "https://shmtransmissie.nl",
  url_limit: 100,
  state: "completed",
  page_count: 2,
  created_at: "2026-06-14T10:00:00Z",
  completed_at: "2026-06-14T10:01:00Z",
};

describe("CrawlPage", () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest
      .mockResolvedValueOnce({ items: [run] })
      .mockResolvedValueOnce({
        run,
        pages: [
          { id: "page-1", url: "https://shmtransmissie.nl", status_code: 200 },
          {
            id: "page-2",
            url: "https://shmtransmissie.nl/contact",
            status_code: 200,
          },
        ],
        issues: [
          {
            id: "issue-1",
            issue_type: "missing_title",
            severity: "high",
            message: "De gecrawlde pagina heeft geen title.",
          },
          {
            id: "issue-2",
            issue_type: "orphan_candidate",
            severity: "medium",
            message: "Geen interne inkomende link gevonden.",
          },
        ],
      });
  });

  it("loads real crawl history and filters technical issues", async () => {
    render(<CrawlPage projectId="shm" />);

    expect(await screen.findByText("2 pagina's")).toBeVisible();
    expect(screen.getByText("De gecrawlde pagina heeft geen title.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Hoge impact" }));
    expect(
      screen.queryByText("Geen interne inkomende link gevonden."),
    ).not.toBeInTheDocument();
  });

  it("starts a crawl through the project API", async () => {
    apiRequest
      .mockResolvedValueOnce({ ...run, id: "crawl-2" })
      .mockResolvedValueOnce({ items: [{ ...run, id: "crawl-2" }] })
      .mockResolvedValueOnce({
        run: { ...run, id: "crawl-2" },
        pages: [],
        issues: [],
      });
    render(<CrawlPage projectId="shm" />);
    await screen.findByText("2 pagina's");

    fireEvent.click(screen.getByRole("button", { name: "Nieuwe crawl" }));

    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith(
        "/projects/shm/crawls",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });
});

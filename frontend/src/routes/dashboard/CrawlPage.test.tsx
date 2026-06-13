import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CrawlPage } from "./CrawlPage";

describe("CrawlPage", () => {
  it("shows crawl history and filters technical issues", () => {
    render(<CrawlPage />);

    expect(
      screen.getByRole("heading", { name: "Technische crawl" }),
    ).toBeVisible();
    expect(screen.getByText("2.184 pagina's")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Hoge impact" }));

    expect(screen.getByText("Gebroken interne links")).toBeVisible();
    expect(screen.queryByText("Dubbele descriptions")).not.toBeInTheDocument();
  });
});

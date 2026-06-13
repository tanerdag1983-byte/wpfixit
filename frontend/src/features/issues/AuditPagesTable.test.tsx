import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuditPagesTable } from "./AuditPagesTable";

const pages = [
  {
    id: "1",
    title: "Transmissie revisie",
    url: "https://example.com/revisie",
    status: "publish",
    pageType: "service",
    priority: "high",
    score: 55,
  },
  {
    id: "2",
    title: "Nieuws",
    url: "https://example.com/nieuws",
    status: "draft",
    pageType: "blog",
    priority: "low",
    score: 82,
  },
];

describe("AuditPagesTable", () => {
  it("combines search, status, type, priority, and score filters", () => {
    render(<AuditPagesTable pages={pages} />);

    fireEvent.change(screen.getByLabelText("Pagina zoeken"), {
      target: { value: "revisie" },
    });
    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "publish" },
    });
    fireEvent.change(screen.getByLabelText("Paginatype"), {
      target: { value: "service" },
    });
    fireEvent.change(screen.getByLabelText("Prioriteit"), {
      target: { value: "high" },
    });
    fireEvent.change(screen.getByLabelText("Maximale score"), {
      target: { value: "70" },
    });

    expect(screen.getByText("Transmissie revisie")).toBeVisible();
    expect(screen.queryByText("Nieuws")).not.toBeInTheDocument();
  });
});

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProposalStageList } from "./ProposalStageList";

describe("ProposalStageList", () => {
  it("shows ordered stage state and bounded field recovery", () => {
    const retryValidation = vi.fn();
    const editField = vi.fn();

    render(
      <ProposalStageList
        busy={false}
        fieldErrors={[{
          fieldId: "acf:hero:label",
          label: "Hero-label",
          message: "bevat niet-toegestane opmaak",
        }]}
        onEditField={editField}
        onRetryText={vi.fn()}
        onRetryValidation={retryValidation}
        stages={[
          { name: "template", state: "ready", retry_count: 0 },
          { name: "text", state: "ready", retry_count: 0 },
          { name: "validation", state: "attention", retry_count: 0 },
        ]}
      />,
    );

    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      expect.stringContaining("Template gereed"),
      expect.stringContaining("Tekst gereed"),
      expect.stringContaining("Gevalideerd"),
      expect.stringContaining("Hero-label bevat niet-toegestane opmaak"),
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Waarde aanpassen" }));
    fireEvent.click(screen.getByRole("button", {
      name: "Validatie opnieuw uitvoeren",
    }));
    expect(editField).toHaveBeenCalledWith("acf:hero:label");
    expect(retryValidation).toHaveBeenCalledOnce();
  });

  it("offers a text retry only for a failed text stage", () => {
    const retryText = vi.fn();

    render(
      <ProposalStageList
        busy={false}
        fieldErrors={[]}
        onEditField={vi.fn()}
        onRetryText={retryText}
        onRetryValidation={vi.fn()}
        stages={[
          { name: "template", state: "ready", retry_count: 0 },
          { name: "text", state: "failed", retry_count: 1 },
          { name: "validation", state: "pending", retry_count: 0 },
        ]}
      />,
    );

    fireEvent.click(screen.getByRole("button", {
      name: "Tekst opnieuw genereren",
    }));
    expect(retryText).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", {
      name: "Validatie opnieuw uitvoeren",
    })).not.toBeInTheDocument();
  });
});

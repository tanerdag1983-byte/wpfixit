import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CreateProjectDialog } from "./CreateProjectDialog";

describe("CreateProjectDialog", () => {
  it("submits a trimmed project name and domain", () => {
    const onSubmit = vi.fn();
    render(<CreateProjectDialog onClose={() => undefined} onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText("Projectnaam"), {
      target: { value: "  Nieuwe website  " },
    });
    fireEvent.change(screen.getByLabelText("Domein"), {
      target: { value: "https://nieuw.example/" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Project aanmaken" }));

    expect(onSubmit).toHaveBeenCalledWith({
      name: "Nieuwe website",
      domain: "https://nieuw.example",
    });
  });
});

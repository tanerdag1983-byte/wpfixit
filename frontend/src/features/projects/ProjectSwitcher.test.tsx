import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProjectSwitcher } from "./ProjectSwitcher";

describe("ProjectSwitcher", () => {
  it("selects a project and opens project creation", () => {
    const onSelect = vi.fn();
    const onCreate = vi.fn();
    render(
      <ProjectSwitcher
        projects={[
          {
            id: "project-1",
            organizationId: "org-1",
            name: "SHM Transmissie",
            domain: "https://shmtransmissie.nl",
          },
          {
            id: "project-2",
            organizationId: "org-1",
            name: "Tweede Site",
            domain: "https://tweede.example",
          },
        ]}
        activeProjectId="project-1"
        onSelect={onSelect}
        onCreate={onCreate}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Project wijzigen" }));
    fireEvent.click(
      screen.getByRole("menuitem", {
        name: "Tweede Sitetweede.example",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Nieuw project" }));

    expect(onSelect).toHaveBeenCalledWith("project-2");
    expect(onCreate).toHaveBeenCalledOnce();
  });
});

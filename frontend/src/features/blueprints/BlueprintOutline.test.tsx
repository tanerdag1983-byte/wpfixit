import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BlueprintOutline } from "./BlueprintOutline";

const schema = {
  schema_version: "blueprint-v1" as const,
  blocks: [
    {
      id: "hero",
      layout: "hero_algemeen",
      label: "Hero (algemeen)",
      semantic_role: "hero" as const,
      fields: [
        {
          id: "hero-title",
          path: "page_blocks/0/title",
          label: "Titel",
          value_type: "heading" as const,
          current_value: "Transmissie revisie",
          required: true,
          max_length: 180,
        },
      ],
    },
  ],
};

describe("BlueprintOutline", () => {
  it("saves semantic roles without exposing structural controls", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<BlueprintOutline schema={schema} onSave={onSave} />);

    fireEvent.click(screen.getByRole("button", { name: /Hero \(algemeen\)/ }));
    expect(screen.getByText("page_blocks/0/title")).toBeVisible();
    expect(
      screen.getByText("Afbeeldingen, vormgeving en builderstructuur blijven behouden."),
    ).toBeVisible();
    expect(screen.queryByLabelText("Builderpad wijzigen")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Rol voor Hero (algemeen)"), {
      target: { value: "introduction" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Rollen opslaan" }));

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({ hero: "introduction" }),
    );
  });

  it("restores server roles when saving is rejected", async () => {
    const onSave = vi.fn().mockResolvedValue(false);
    render(<BlueprintOutline schema={schema} onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: /Hero \(algemeen\)/ }));
    const role = screen.getByLabelText("Rol voor Hero (algemeen)");
    fireEvent.change(role, { target: { value: "introduction" } });
    fireEvent.click(screen.getByRole("button", { name: "Rollen opslaan" }));

    await waitFor(() => expect(role).toHaveValue("hero"));
  });

  it("disables role saving while another blueprint mutation is active", () => {
    render(<BlueprintOutline disabled schema={schema} onSave={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Rollen opslaan" })).toBeDisabled();
  });
});

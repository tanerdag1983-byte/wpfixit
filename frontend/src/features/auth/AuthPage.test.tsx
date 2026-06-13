import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuthPage } from "./AuthPage";

describe("AuthPage", () => {
  it("offers Google and Microsoft SSO", () => {
    render(<AuthPage />);

    expect(screen.getByRole("heading", { name: "Veilig inloggen" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Doorgaan met Google" })).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Doorgaan met Microsoft" }),
    ).toBeVisible();
  });
});

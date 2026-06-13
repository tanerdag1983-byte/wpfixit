import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AuthGate } from "./AuthGate";

describe("AuthGate", () => {
  afterEach(() => {
    window.location.hash = "";
  });

  it("shows the login screen on the login preview route", () => {
    window.location.hash = "#login";

    render(
      <AuthGate>
        <p>Beveiligde inhoud</p>
      </AuthGate>,
    );

    expect(
      screen.getByRole("heading", { name: "Veilig inloggen" }),
    ).toBeVisible();
    expect(screen.queryByText("Beveiligde inhoud")).not.toBeInTheDocument();
  });
});

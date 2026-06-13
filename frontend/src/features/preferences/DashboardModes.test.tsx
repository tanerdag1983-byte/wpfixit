import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { I18nProvider } from "./i18n";
import { DashboardModes } from "./DashboardModes";
import { preferenceStorage } from "./storage";

describe("DashboardModes", () => {
  afterEach(() => preferenceStorage.clear());
  it("restores the signed-in user's dashboard view", async () => {
    preferenceStorage.set("dashboard-view", "action");

    render(
      <I18nProvider locale="nl">
        <DashboardModes />
      </I18nProvider>,
    );

    expect(
      await screen.findByRole("heading", {
        name: "Wat verdient vandaag aandacht?",
      }),
    ).toBeVisible();
  });
});

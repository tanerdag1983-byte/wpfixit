import { createContext } from "react";

export type Locale = "nl" | "en";

export const messages = {
  nl: {
    overview: "Overzicht",
    analytics: "Analytics",
    actions: "Acties",
    opportunities: "Kansen",
    priorities: "SEO-prioriteiten",
    settings: "Instellingen",
    analyticsHeading: "Wat gebeurt er in je data?",
    actionHeading: "Wat verdient vandaag aandacht?",
    hybridHeading: "SEO command center",
    analyticsView: "Analytics",
    actionView: "Acties",
    hybridView: "Hybride",
  },
  en: {
    overview: "Overview",
    analytics: "Analytics",
    actions: "Actions",
    opportunities: "Opportunities",
    priorities: "SEO priorities",
    settings: "Settings",
    analyticsHeading: "What is happening in your data?",
    actionHeading: "What needs attention today?",
    hybridHeading: "SEO command center",
    analyticsView: "Analytics",
    actionView: "Actions",
    hybridView: "Hybrid",
  },
} as const;

export type MessageKey = keyof (typeof messages)["nl"];

export const I18nContext = createContext({
  locale: "nl" as Locale,
  t: (key: MessageKey) => messages.nl[key] as string,
});

import type { ReactNode } from "react";

import { I18nContext, messages, type Locale } from "./i18n-core";
export function I18nProvider({
  locale,
  children,
}: {
  locale: Locale;
  children: ReactNode;
}) {
  return (
    <I18nContext.Provider
      value={{ locale, t: (key) => messages[locale][key] }}
    >
      {children}
    </I18nContext.Provider>
  );
}

export type BrandSettings = {
  name: string;
  primaryColor: string;
  accentColor: string;
};

export const defaultBrand: BrandSettings = {
  name:
    (import.meta.env.VITE_APP_NAME as string | undefined) ?? "WP FixPilot",
  primaryColor:
    (import.meta.env.VITE_PRIMARY_COLOR as string | undefined) ?? "#173b2d",
  accentColor:
    (import.meta.env.VITE_ACCENT_COLOR as string | undefined) ?? "#d7ff54",
};

export function applyBrand(settings: BrandSettings) {
  document.documentElement.style.setProperty(
    "--forest",
    settings.primaryColor,
  );
  document.documentElement.style.setProperty(
    "--accent",
    settings.accentColor,
  );
  document.title = settings.name;
}

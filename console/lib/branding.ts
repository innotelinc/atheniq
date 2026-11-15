import type { BrandSettings, LogoPlacement, Settings } from "./types";

/**
 * The public site is white-label: every name, mark, colour and domain it shows
 * comes from these settings, not from the code. The console keeps its own
 * AthenIQ chrome — this is the school's face.
 */

const HEX = /^#[0-9a-f]{6}$/i;
const PLACEMENTS: LogoPlacement[] = ["left", "center", "right"];

export function brandOf(settings: Settings): BrandSettings {
  const b = (settings.brand ?? {}) as Partial<BrandSettings>;
  return {
    siteName: (b.siteName ?? "").trim() || settings.org || "AthenIQ Institute",
    tagline: (b.tagline ?? "").trim() || "An online university",
    logoUrl: (b.logoUrl ?? "").trim(),
    logoText: (b.logoText ?? "").trim().slice(0, 3),
    logoPlacement: PLACEMENTS.includes(b.logoPlacement as LogoPlacement)
      ? (b.logoPlacement as LogoPlacement)
      : "left",
    accent: HEX.test(b.accent ?? "") ? (b.accent as string) : "#10b981",
    supportEmail: (b.supportEmail ?? "").trim() || settings.signer?.email || "",
    poweredBy: b.poweredBy !== false,
    domain: normalizeDomain(b.domain ?? "") || "atheniq.institute",
  };
}

export function normalizeDomain(value: string): string {
  return value
    .trim()
    .replace(/^https?:\/\//i, "")
    .replace(/\/.*$/, "")
    .replace(/:\d+$/, "")
    .toLowerCase();
}

/**
 * Where the console itself answers. The brand domain serves the public site, so
 * a link to a console-only page (/staff, /security) must not use it. Set
 * CONSOLE_ORIGIN for a host that is not the registrar subdomain.
 */
export function consoleOrigin(domain: string): string {
  const configured = (process.env.CONSOLE_ORIGIN || "").trim().replace(/\/+$/, "");
  if (configured) return configured;
  const host = normalizeDomain(domain);
  return host ? `https://registrar.${host}` : "http://localhost:3100";
}

/** "AthenIQ Institute" → "AI"; override with logoText. */
export function monogram(brand: BrandSettings): string {
  if (brand.logoText) return brand.logoText;
  const letters = brand.siteName
    .split(/\s+/)
    .filter((word) => /[A-Za-z0-9]/.test(word))
    .map((word) => word[0]);
  return (letters.join("") || "A").slice(0, 2).toUpperCase();
}

/** Public hosts this build answers as, from PUBLIC_SITE_HOSTS. */
export function publicHosts(): string[] {
  return (process.env.PUBLIC_SITE_HOSTS || "atheniq.institute,www.atheniq.institute")
    .split(",")
    .map((host) => normalizeDomain(host))
    .filter(Boolean);
}

/** Inline custom properties so the public site can be re-coloured per tenant. */
export function brandVars(brand: BrandSettings): Record<string, string> {
  return {
    "--brand": brand.accent,
    "--brand-soft": brand.accent,
    "--site-accent": brand.accent,
  };
}

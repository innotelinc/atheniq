import { normalizeDomain } from "./branding";

/**
 * Sign-in is limited to the domains the school has registered. The check is on
 * the domain as a whole (`innotel.us`), with subdomains allowed — never a bare
 * suffix match, so `evil-innotel.us` cannot pass itself off as `innotel.us`.
 */

export function emailDomain(email: string): string {
  const value = (email || "").trim().toLowerCase();
  const at = value.lastIndexOf("@");
  if (at < 1 || at === value.length - 1) return "";
  return normalizeDomain(value.slice(at + 1));
}

export function normaliseDomains(domains: string[]): string[] {
  return [...new Set(domains.map((domain) => normalizeDomain(domain)).filter(Boolean))];
}

export function emailAllowed(email: string, allowed: string[]): boolean {
  const domain = emailDomain(email);
  if (!domain) return false;
  return normaliseDomains(allowed).some(
    (entry) => domain === entry || domain.endsWith(`.${entry}`),
  );
}

export function describeDomains(domains: string[]): string {
  const list = normaliseDomains(domains);
  if (!list.length) return "no domains are registered";
  return list.map((domain) => `@${domain}`).join(", ");
}

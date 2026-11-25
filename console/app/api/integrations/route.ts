import { getDb, logActivity, mutate, publicSettings } from "@/lib/store";
import { allowed, currentActor } from "@/lib/current-staff";
import { fail, ok, str } from "@/lib/api";
import { normalizeDomain } from "@/lib/branding";
import type { LogoPlacement, Settings } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET() {
  const db = getDb();
  return ok(publicSettings(db.settings));
}

function keepSecret(incoming: unknown, current: string): string {
  const value = str(incoming);
  if (!value || value.includes("••••")) return current;
  return value;
}

function placement(value: unknown, fallback: LogoPlacement): LogoPlacement {
  return value === "left" || value === "center" || value === "right" ? value : fallback;
}

function bool(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

export async function PUT(request: Request) {
  if (!(await allowed("settings"))) return fail("Only a registrar can change integrations.", 403);
  const body = (await request.json().catch(() => null)) as Partial<Settings> | null;
  if (!body) return fail("Invalid body.");
  const actor = await currentActor();

  const updated = await mutate((db) => {
    const s = db.settings;
    if (body.org !== undefined) s.org = str(body.org) || s.org;
    if (body.orgShort !== undefined) s.orgShort = str(body.orgShort) || s.orgShort;
    if (body.defaultTerm !== undefined) s.defaultTerm = str(body.defaultTerm) || s.defaultTerm;
    if (body.tuitionPerCreditCents !== undefined) s.tuitionPerCreditCents = Number(body.tuitionPerCreditCents) || s.tuitionPerCreditCents;
    if (body.applicationFeeCents !== undefined) s.applicationFeeCents = Number(body.applicationFeeCents) || s.applicationFeeCents;
    if (body.graduationFeeCents !== undefined) s.graduationFeeCents = Number(body.graduationFeeCents) || s.graduationFeeCents;

    if (body.lms) {
      s.lms.baseUrl = str(body.lms.baseUrl) || s.lms.baseUrl;
      s.lms.studioUrl = str(body.lms.studioUrl) || s.lms.studioUrl;
      s.lms.catalogUrl = str(body.lms.catalogUrl) || s.lms.catalogUrl;
      s.lms.importUrl = body.lms.importUrl !== undefined ? str(body.lms.importUrl) : s.lms.importUrl;
      s.lms.apiToken = keepSecret(body.lms.apiToken, s.lms.apiToken);
    }
    if (body.signara) {
      s.signara.baseUrl = str(body.signara.baseUrl) || s.signara.baseUrl;
      s.signara.apiKey = keepSecret(body.signara.apiKey, s.signara.apiKey);
      if (body.signara.autoSign !== undefined) s.signara.autoSign = Boolean(body.signara.autoSign);
      if (body.signara.defaultTemplate !== undefined)
        s.signara.defaultTemplate = str(body.signara.defaultTemplate) || s.signara.defaultTemplate;
      if (body.signara.keyExpiresAt !== undefined) {
        const raw = str(body.signara.keyExpiresAt);
        s.signara.keyExpiresAt = /^\d{4}-\d{2}-\d{2}/.test(raw) ? raw : null;
      }
    }
    if (body.ai) {
      s.ai.baseUrl = str(body.ai.baseUrl) || s.ai.baseUrl;
      s.ai.apiKey = keepSecret(body.ai.apiKey, s.ai.apiKey);
      s.ai.model = str(body.ai.model) || s.ai.model;
    }
    if (body.signer) {
      s.signer.name = str(body.signer.name) || s.signer.name;
      s.signer.title = str(body.signer.title) || s.signer.title;
      s.signer.email = str(body.signer.email) || s.signer.email;
    }
    if (body.sites) {
      s.sites.instituteUrl = str(body.sites.instituteUrl) || s.sites.instituteUrl;
      s.sites.coursesUrl = str(body.sites.coursesUrl) || s.sites.coursesUrl;
      s.sites.workforceUrl = str(body.sites.workforceUrl) || s.sites.workforceUrl;
    }

    if (body.brand) {
      const b = body.brand;
      s.brand.siteName = str(b.siteName) || s.brand.siteName;
      if (b.tagline !== undefined) s.brand.tagline = str(b.tagline);
      if (b.logoUrl !== undefined) s.brand.logoUrl = str(b.logoUrl);
      if (b.logoText !== undefined) s.brand.logoText = str(b.logoText).slice(0, 3);
      s.brand.logoPlacement = placement(b.logoPlacement, s.brand.logoPlacement);
      if (b.accent !== undefined) {
        const accent = str(b.accent);
        if (/^#[0-9a-fA-F]{6}$/.test(accent)) s.brand.accent = accent;
      }
      if (b.supportEmail !== undefined) s.brand.supportEmail = str(b.supportEmail);
      s.brand.poweredBy = bool(b.poweredBy, s.brand.poweredBy);
      if (b.domain !== undefined) s.brand.domain = normalizeDomain(str(b.domain)) || s.brand.domain;
    }

    if (body.site) {
      const site = body.site;
      if (site.published !== undefined) {
        const next = Boolean(site.published);
        if (next !== s.site.published) {
          s.site.published = next;
          if (next) s.site.lastPublishedAt = new Date().toISOString();
          logActivity(
            db,
            "site.updated",
            next ? "Published the public website" : "Took the public website offline",
            "site",
            actor,
          );
        }
      }
      if (site.headline !== undefined) s.site.headline = str(site.headline) || s.site.headline;
      if (site.intro !== undefined) s.site.intro = str(site.intro);
      s.site.showPrices = bool(site.showPrices, s.site.showPrices);
      s.site.showPrograms = bool(site.showPrograms, s.site.showPrograms);
      s.site.showVerify = bool(site.showVerify, s.site.showVerify);
      if (site.ctaLabel !== undefined) s.site.ctaLabel = str(site.ctaLabel) || s.site.ctaLabel;
      if (site.ctaHref !== undefined) s.site.ctaHref = str(site.ctaHref) || s.site.ctaHref;
    }

    if (body.auth) {
      if (Array.isArray(body.auth.allowedDomains)) {
        s.auth.allowedDomains = [...new Set(body.auth.allowedDomains.map((domain) => normalizeDomain(str(domain))).filter(Boolean))];
      }
      if (body.auth.require2fa !== undefined) s.auth.require2fa = Boolean(body.auth.require2fa);
      logActivity(db, "settings.updated", "Updated the sign-in policy", "auth", actor);
    }

    if (body.mail) {
      if (body.mail.digestTo !== undefined) s.mail.digestTo = str(body.mail.digestTo);
      if (body.mail.cadenceDays !== undefined) {
        const cadence = Number(body.mail.cadenceDays);
        if (Number.isFinite(cadence)) s.mail.cadenceDays = Math.min(90, Math.max(1, Math.round(cadence)));
      }
    }

    logActivity(db, "settings.updated", "Updated platform integrations", "settings", actor);
    return publicSettings(s);
  });

  return ok(updated);
}

import { probeModel } from "./ai";
import { probeSignara } from "./signara";
import type { Settings } from "./types";

/**
 * Integration health: is each pipeline reachable right now, and is the Signara
 * key about to expire? The console records when the current key expires, so a
 * key that is a year out still shows a countdown instead of surprising someone
 * mid-award.
 */

export type HealthLevel = "ok" | "warn" | "bad" | "muted";

export interface KeyWindow {
  level: HealthLevel;
  label: string;
  detail: string;
  days: number | null;
  expiresAt: string | null;
}

const DAY = 86_400_000;

export function expiryWindow(expiresAt: string | null | undefined): KeyWindow {
  if (!expiresAt) {
    return {
      level: "muted",
      label: "Expiry not recorded",
      detail: "Record when the current Signara key expires so rotation is planned, not discovered.",
      days: null,
      expiresAt: null,
    };
  }
  const at = new Date(expiresAt).getTime();
  if (!Number.isFinite(at)) {
    return { level: "muted", label: "Expiry unreadable", detail: "Enter the expiry as a date.", days: null, expiresAt };
  }
  const days = Math.ceil((at - Date.now()) / DAY);
  const date = expiresAt.slice(0, 10);
  if (days <= 0) {
    return {
      level: "bad",
      label: `Expired ${Math.abs(days)} day${Math.abs(days) === 1 ? "" : "s"} ago`,
      detail: `The key expired on ${date}. Awards will stop at the upload step until a new key is set.`,
      days,
      expiresAt,
    };
  }
  if (days <= 30) {
    return {
      level: "warn",
      label: `${days} day${days === 1 ? "" : "s"} left`,
      detail: `Expires ${date}. Mint a replacement in Signara and paste it into Integrations before then.`,
      days,
      expiresAt,
    };
  }
  return { level: "ok", label: `${days} days left`, detail: `Expires ${date}.`, days, expiresAt };
}

export interface IntegrationCheck {
  id: "signara" | "ai" | "lms";
  label: string;
  ok: boolean;
  configured: boolean;
  detail: string;
  http: number | null;
}

export async function probeLms(settings: Settings["lms"]): Promise<IntegrationCheck> {
  const base = settings.baseUrl.replace(/\/+$/, "");
  if (!base) {
    return { id: "lms", label: "Course engine", ok: false, configured: false, detail: "No LMS URL configured.", http: null };
  }
  try {
    const response = await fetch(`${base}/api/courses/v1/courses/?page_size=1`, {
      headers: settings.apiToken ? { Authorization: `Bearer ${settings.apiToken}` } : {},
      signal: AbortSignal.timeout(10_000),
    });
    const text = await response.text();
    let count: number | null = null;
    try {
      const parsed = JSON.parse(text) as { results?: unknown[]; pagination?: { count?: number } };
      count = parsed.pagination?.count ?? parsed.results?.length ?? null;
    } catch {
      /* some catalogs answer HTML */
    }
    return {
      id: "lms",
      label: "Course engine",
      ok: response.ok,
      configured: true,
      http: response.status,
      detail: response.ok ? `Catalog answered${count !== null ? ` — ${count} course(s)` : ""}.` : `HTTP ${response.status}: ${text.slice(0, 140)}`,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return { id: "lms", label: "Course engine", ok: false, configured: true, detail: `Could not reach ${base}: ${message}`, http: 0 };
  }
}

export interface IntegrationHealth {
  window: KeyWindow;
  checks: IntegrationCheck[];
  healthy: boolean;
}

export async function integrationHealth(settings: Settings): Promise<IntegrationHealth> {
  const [signara, ai, lms] = await Promise.all([
    probeSignara(settings.signara),
    probeModel(settings.ai),
    probeLms(settings.lms),
  ]);

  const checks: IntegrationCheck[] = [
    {
      id: "signara",
      label: "Signara signing",
      ok: signara.ok,
      configured: Boolean(settings.signara.apiKey),
      detail: signara.detail,
      http: signara.http,
    },
    {
      id: "ai",
      label: "Model gateway",
      ok: ai.ok,
      configured: Boolean(settings.ai.apiKey),
      detail: ai.detail,
      http: null,
    },
    { ...lms },
  ];

  const window = expiryWindow(settings.signara.keyExpiresAt);
  const healthy = checks.every((check) => check.ok) && window.level !== "bad";
  return { window, checks, healthy };
}

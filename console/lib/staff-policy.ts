import type { StaffRole } from "./types";

/**
 * Role policy, deliberately tiny and dependency-free: middleware and route
 * handlers both need it, and neither should pull in scrypt or the store.
 */

export type { StaffRole };

export const ROLE_LABELS: Record<StaffRole, string> = {
  registrar: "Registrar",
  publisher: "Publisher",
};

export const ROLE_DESCRIPTIONS: Record<StaffRole, string> = {
  registrar: "Everything: courses, awards, signing, integrations and staff accounts.",
  publisher: "Creates, revises and publishes courses. Cannot award credentials or change settings.",
};

export const ROLES: StaffRole[] = ["registrar", "publisher"];

export function coerceRole(value: unknown): StaffRole {
  return ROLES.includes(value as StaffRole) ? (value as StaffRole) : "publisher";
}

/** Registrars run the school; publishers write and publish courses. */
export function can(
  role: StaffRole | undefined,
  action: "publish" | "award" | "settings" | "staff",
): boolean {
  if (!role) return false;
  if (role === "registrar") return true;
  return action === "publish";
}

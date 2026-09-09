import type { UserRole } from "@clearcut/contracts";

/**
 * A local reading of the server's role capabilities, used only to decide whether
 * to *offer* a governed control.
 *
 * It is a courtesy, not a boundary. Every governed write is authorized again
 * server-side from the server-provided role, so a stale or wrong reading here
 * cannot grant anything — it can only show a control that is then refused.
 */

/** `member:manage` — operational organization settings. Owner and Admin. */
export function canManageOrganizationSettings(role: UserRole | null | undefined): boolean {
  return role === "owner" || role === "admin";
}

/**
 * `governance:manage` — protected configuration lifecycle and the learning
 * candidate lifecycle. Owner only; no other role holds it.
 */
export function canManageGovernance(role: UserRole | null | undefined): boolean {
  return role === "owner";
}

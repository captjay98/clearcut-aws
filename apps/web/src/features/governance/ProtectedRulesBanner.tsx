import React from "react";
import { Banner } from "../../components/ds";

/**
 * The human-only boundary, stated where governed configuration is shown.
 *
 * This is protected language in its own right: the list of scopes is the one the
 * server enforces, and it is not softened or shortened per surface.
 */
export function ProtectedRulesBanner() {
  return (
    <Banner
      tone="is-danger"
      icon="⚖"
      title="Some things only a person may change"
      message="Permissions, sign-off policy, category definitions, source-authority tiers, evidence schemas, deterministic blocking rules, retention and privacy settings, and legal-boundary language are human-only and Owner-governed. A learning candidate may propose query phrasing and examples; it cannot touch anything on this list."
    />
  );
}

export default ProtectedRulesBanner;

import React from "react";

export interface BadgeProps {
  label: string;
  variant?: "neutral" | "primary" | "success" | "warning" | "danger";
  size?: "sm" | "md";
}

/**
 * The design system has one badge size, so `size` is accepted for API
 * compatibility and intentionally does not change the rendering.
 */
const VARIANT_TONE: Record<NonNullable<BadgeProps["variant"]>, string> = {
  neutral: "",
  primary: "is-accent",
  success: "is-success",
  warning: "is-warning",
  danger: "is-danger",
};

export function Badge({ label, variant = "neutral" }: BadgeProps) {
  return <span className={`badge ${VARIANT_TONE[variant]}`.trim()}>{label}</span>;
}

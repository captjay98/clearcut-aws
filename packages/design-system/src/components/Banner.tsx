import React, { ReactNode } from "react";

export interface BannerProps {
  type?: "info" | "warning" | "danger" | "success";
  title?: string;
  children: ReactNode;
}

const TYPE_TONE: Record<NonNullable<BannerProps["type"]>, string> = {
  info: "",
  warning: "is-warning",
  danger: "is-danger",
  success: "is-success",
};

const TYPE_ICON: Record<NonNullable<BannerProps["type"]>, string> = {
  info: "ℹ",
  warning: "⚠",
  danger: "⚠",
  success: "✓",
};

export function Banner({ type = "info", title, children }: BannerProps) {
  return (
    <div className={`banner ${TYPE_TONE[type]}`.trim()} role="alert">
      <span className="banner-icon" aria-hidden="true">
        {TYPE_ICON[type]}
      </span>
      <div className="banner-body">
        {title && <strong>{title}</strong>}
        <div>{children}</div>
      </div>
    </div>
  );
}

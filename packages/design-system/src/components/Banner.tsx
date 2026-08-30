import React, { ReactNode } from "react";

export interface BannerProps {
  type?: "info" | "warning" | "danger" | "success";
  title?: string;
  children: ReactNode;
}

export function Banner({ type = "info", title, children }: BannerProps) {
  const styles = {
    info: "bg-blue-50 dark:bg-blue-950/40 border-blue-200 dark:border-blue-900 text-blue-900 dark:text-blue-200",
    warning: "bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-900 text-amber-900 dark:text-amber-200",
    danger: "bg-rose-50 dark:bg-rose-950/40 border-rose-200 dark:border-rose-900 text-rose-900 dark:text-rose-200",
    success: "bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-900 text-emerald-900 dark:text-emerald-200",
  };

  return (
    <div className={`p-4 rounded-lg border text-sm ${styles[type]}`} role="alert">
      {title && <h3 className="font-semibold mb-1">{title}</h3>}
      <div>{children}</div>
    </div>
  );
}

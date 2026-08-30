import React from "react";

export interface BadgeProps {
  label: string;
  variant?: "neutral" | "primary" | "success" | "warning" | "danger";
  size?: "sm" | "md";
}

export function Badge({ label, variant = "neutral", size = "sm" }: BadgeProps) {
  const variantStyles = {
    neutral: "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300",
    primary: "bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300",
    success: "bg-emerald-100 dark:bg-emerald-900/50 text-emerald-700 dark:text-emerald-300",
    warning: "bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-300",
    danger: "bg-rose-100 dark:bg-rose-900/50 text-rose-700 dark:text-rose-300",
  };

  const sizeStyles = {
    sm: "px-2 py-0.5 text-xs",
    md: "px-2.5 py-1 text-sm",
  };

  return (
    <span
      className={`inline-flex items-center font-medium rounded-full ${variantStyles[variant]} ${sizeStyles[size]}`}
    >
      {label}
    </span>
  );
}

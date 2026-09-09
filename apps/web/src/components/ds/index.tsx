/**
 * Design-system primitives mirroring the helper functions in the canonical mock
 * (misc/clearcut-flow/assets/app.js): page(), section(), card(), statGrid(),
 * dataTable(), emptyState(), banner(), tabsBar(), badge(), progress(), avatar()
 * and breadcrumb().
 *
 * These emit the same class vocabulary the mock's stylesheet already styles, so
 * surfaces are composed from them rather than restating layout per screen.
 */
import React from "react";
import { Link } from "@tanstack/react-router";

export type Tone = "" | "is-success" | "is-warning" | "is-danger" | "is-accent" | "is-primary";

/* ── Breadcrumb ─────────────────────────────────────────────────────────── */

export interface TrailEntry {
  label: string;
  /** Omitted on the final entry, which renders as aria-current="page". */
  to?: string;
  params?: Record<string, string>;
}

export function Breadcrumb({ trail }: { trail: readonly TrailEntry[] }) {
  return (
    <nav className="breadcrumb" aria-label="Breadcrumb">
      {trail.map((entry, index) => {
        const last = index === trail.length - 1;
        if (last || !entry.to) {
          return (
            <span key={entry.label} aria-current="page">
              {entry.label}
            </span>
          );
        }
        return (
          <React.Fragment key={entry.label}>
            <Link to={entry.to} params={entry.params}>
              {entry.label}
            </Link>
            <span className="breadcrumb-sep" aria-hidden="true">
              /
            </span>
          </React.Fragment>
        );
      })}
    </nav>
  );
}

/* ── Page ───────────────────────────────────────────────────────────────── */

export interface PageProps {
  title: string;
  eyebrow?: string;
  lede?: React.ReactNode;
  /** Renders the heading for assistive technology only. */
  srTitle?: boolean;
  trail?: readonly TrailEntry[];
  actions?: React.ReactNode;
  notice?: React.ReactNode;
  width?: "" | "narrow" | "flush";
  children?: React.ReactNode;
}

export function Page({
  title,
  eyebrow,
  lede,
  srTitle = false,
  trail,
  actions,
  notice,
  width = "",
  children,
}: PageProps) {
  return (
    <div className={`page ${width}`.trim()}>
      <header className="page-head">
        {trail && <Breadcrumb trail={trail} />}
        {srTitle ? (
          <h1 id="route-heading" className="sr-only" tabIndex={-1}>
            {title}
          </h1>
        ) : (
          <div className="page-head-row">
            <div>
              {eyebrow && <span className="eyebrow">{eyebrow}</span>}
              <h1 id="route-heading" tabIndex={-1}>
                {title}
              </h1>
              {lede && <p className="page-lede">{lede}</p>}
            </div>
            {actions && <div className="page-head-actions">{actions}</div>}
          </div>
        )}
      </header>
      {notice && <div className="page-notice">{notice}</div>}
      {children}
    </div>
  );
}

/* ── Section ────────────────────────────────────────────────────────────── */

export interface SectionProps {
  title?: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  /** Anchor id, so a section rail can address the group directly. */
  id?: string;
  children: React.ReactNode;
}

export function Section({ title, description, actions, id, children }: SectionProps) {
  const hasHead = Boolean(title || actions || description);
  return (
    <section className="section" {...(id ? { id: `sec-${id}`, tabIndex: -1 } : {})}>
      {hasHead && (
        <div className="section-head">
          <div>
            {title && <h2>{title}</h2>}
            {description && <p>{description}</p>}
          </div>
          {actions && <div className="cluster">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

/* ── Card ───────────────────────────────────────────────────────────────── */

export interface CardProps {
  title?: string;
  eyebrow?: string;
  badge?: React.ReactNode;
  accent?: boolean;
  quiet?: boolean;
  actions?: React.ReactNode;
  className?: string;
  /** Stable hook for tests that need to address a specific card. */
  testId?: string;
  children: React.ReactNode;
}

export function Card({
  title,
  eyebrow,
  badge,
  accent = false,
  quiet = false,
  actions,
  className = "",
  testId,
  children,
}: CardProps) {
  const hasHead = Boolean(title || badge || eyebrow);
  const classes = ["card", accent && "card-accent", quiet && "card-quiet", className]
    .filter(Boolean)
    .join(" ");
  return (
    <article className={classes} data-testid={testId}>
      {hasHead && (
        <div className="card-head">
          <div>
            {eyebrow && <span className="eyebrow">{eyebrow}</span>}
            {title && <h2>{title}</h2>}
          </div>
          {badge}
        </div>
      )}
      {children}
      {actions && <div className="cluster gap-t-4 card-actions">{actions}</div>}
    </article>
  );
}

/* ── Stats ──────────────────────────────────────────────────────────────── */

export interface Stat {
  label: string;
  value: string | number;
  hint?: string;
  tone?: Tone;
  /** When present the whole stat becomes a link to the underlying records. */
  to?: string;
  params?: Record<string, string>;
}

export function StatGrid({ stats, columns = 4 }: { stats: readonly Stat[]; columns?: 2 | 3 | 4 }) {
  return (
    <div className={`grid grid-${columns}`}>
      {stats.map((stat) => {
        const inner = (
          <>
            <span className="stat-label">{stat.label}</span>
            <span className="stat-value">{String(stat.value)}</span>
            {stat.hint && <span className="stat-hint">{stat.hint}</span>}
          </>
        );
        if (stat.to) {
          return (
            <Link
              key={stat.label}
              to={stat.to}
              params={stat.params}
              className={`stat stat-link ${stat.tone ?? ""}`.trim()}
              aria-label={`${stat.label}: ${stat.value} — open the underlying records`}
            >
              {inner}
              <span className="stat-go" aria-hidden="true">
                →
              </span>
            </Link>
          );
        }
        return (
          <div key={stat.label} className={`stat ${stat.tone ?? ""}`.trim()}>
            {inner}
          </div>
        );
      })}
    </div>
  );
}

/* ── Data table ─────────────────────────────────────────────────────────── */

export interface Column {
  label: string;
  align?: "left" | "right";
}

export function DataTable({
  columns,
  rows,
  caption,
}: {
  columns: readonly Column[];
  rows: readonly React.ReactNode[][];
  caption?: string;
}) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.label}
                scope="col"
                className={column.align === "right" ? "cell-actions" : undefined}
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            // Row order is the table's identity here; cells carry no stable key.
            // eslint-disable-next-line react/no-array-index-key
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                // eslint-disable-next-line react/no-array-index-key
                <td
                  key={cellIndex}
                  data-label={columns[cellIndex]?.label}
                  className={columns[cellIndex]?.align === "right" ? "cell-actions" : undefined}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Empty state ────────────────────────────────────────────────────────── */

export function EmptyState({
  icon = "◦",
  title,
  description,
  action,
}: {
  icon?: string;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon" aria-hidden="true">
        {icon}
      </span>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}

/* ── Banner ─────────────────────────────────────────────────────────────── */

export function Banner({
  tone = "",
  icon = "ℹ",
  title,
  message,
  action,
  /** Set for error banners so the message is announced immediately. */
  role,
  /**
   * Exposes the title as a heading. The mock styles banner titles as <strong>,
   * which is right visually, but where a banner announces the outcome of an
   * operation the title is the heading for that outcome and should be reachable
   * as one. Opt-in so routine advisories stay out of the heading outline.
   */
  titleIsHeading = false,
  className = "",
}: {
  tone?: Tone;
  icon?: string;
  title?: string;
  message?: React.ReactNode;
  action?: React.ReactNode;
  role?: "alert" | "status";
  titleIsHeading?: boolean;
  className?: string;
}) {
  return (
    <div className={`banner ${tone} ${className}`.trim()} role={role}>
      <span className="banner-icon" aria-hidden="true">
        {icon}
      </span>
      <div className="banner-body">
        {title &&
          (titleIsHeading ? (
            <strong role="heading" aria-level={3}>
              {title}
            </strong>
          ) : (
            <strong>{title}</strong>
          ))}
        {message && <p>{message}</p>}
      </div>
      {action && <div className="cluster">{action}</div>}
    </div>
  );
}

/* ── Tabs ───────────────────────────────────────────────────────────────── */

export interface TabItem {
  value: string;
  label: string;
  count?: number;
}

export function TabsBar({
  items,
  active,
  onChange,
  label,
}: {
  items: readonly TabItem[];
  active: string;
  onChange: (value: string) => void;
  label: string;
}) {
  return (
    <div className="tabs" role="group" aria-label={label}>
      {items.map((item) => (
        <button
          key={item.value}
          className="tab"
          type="button"
          aria-pressed={item.value === active}
          onClick={() => onChange(item.value)}
        >
          {item.label}
          {item.count !== undefined ? ` (${item.count})` : ""}
        </button>
      ))}
    </div>
  );
}

/* ── Small pieces ───────────────────────────────────────────────────────── */

export function Badge({ children, tone = "" }: { children: React.ReactNode; tone?: Tone }) {
  return <span className={`badge ${tone}`.trim()}>{children}</span>;
}

export function Progress({ percent }: { percent: number }) {
  const clamped = Math.max(0, Math.min(100, Math.round(percent)));
  return (
    <div className="progress" role="img" aria-label={`${clamped}% complete`}>
      <span style={{ width: `${clamped}%` }} />
    </div>
  );
}

export function Avatar({
  initials,
  label,
  large = false,
}: {
  initials: string;
  label: string;
  large?: boolean;
}) {
  return (
    <span className={`avatar ${large ? "avatar-lg" : ""}`.trim()} title={label} aria-label={label}>
      {initials}
    </span>
  );
}

export function Cluster({
  children,
  between = false,
  className = "",
}: {
  children: React.ReactNode;
  between?: boolean;
  className?: string;
}) {
  return <div className={`${between ? "cluster-between" : "cluster"} ${className}`.trim()}>{children}</div>;
}

export function Stack({
  children,
  gap = "",
  className = "",
}: {
  children: React.ReactNode;
  gap?: "" | "sm" | "lg";
  className?: string;
}) {
  return <div className={`${gap ? `stack-${gap}` : "stack"} ${className}`.trim()}>{children}</div>;
}

export function Spinner({ label }: { label: string }) {
  return <span className="spinner" role="status" aria-label={label} />;
}

import React from "react";
import { ThemeSwitcher } from "../theme/ThemeSwitcher";

interface PublicShellProps {
  /** Small uppercase kicker above the heading. */
  eyebrow: string;
  title: string;
  lede: React.ReactNode;
  children: React.ReactNode;
}

/**
 * The shell for surfaces that render before an organization exists — the
 * credential screens and onboarding — which the mock places in its public
 * layer. Mirrors the mock's site-header plus a narrow page().
 */
export function PublicShell({ eyebrow, title, lede, children }: PublicShellProps) {
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>

      <header className="site-header">
        <div className="site-header-inner">
          <a className="brand" href="/" aria-label="ClearCut home">
            <span className="slate-mark" aria-hidden="true">
              <span>CC</span>
            </span>
            <span>ClearCut</span>
          </a>
          <div className="header-spacer" />
          <div className="header-actions public-header-actions">
            <ThemeSwitcher />
          </div>
        </div>
        <span className="revision-bar" aria-hidden="true" />
      </header>

      <main id="main-content">
        <div className="page narrow">
          <header className="page-head">
            <div className="page-head-row">
              <div>
                <span className="eyebrow">{eyebrow}</span>
                <h1 id="route-heading" tabIndex={-1}>
                  {title}
                </h1>
                <p className="page-lede">{lede}</p>
              </div>
            </div>
          </header>
          {children}
        </div>
      </main>
    </>
  );
}

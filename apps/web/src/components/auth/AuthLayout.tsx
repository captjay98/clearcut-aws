import React from "react";
import { ThemeSwitcher } from "../theme/ThemeSwitcher";

interface AuthLayoutProps {
  /** Small uppercase kicker above the heading. */
  eyebrow: string;
  title: string;
  lede: string;
  children: React.ReactNode;
}

/**
 * The public shell for the credential surfaces, mirroring the canonical mock's
 * site-header plus a narrow page(). The mock's own auth screen collects no
 * credentials because its identity is simulated, so the header and page
 * furniture come from the mock while the form itself is ours.
 */
export function AuthLayout({ eyebrow, title, lede, children }: AuthLayoutProps) {
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

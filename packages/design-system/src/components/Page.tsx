import React, { ReactNode } from "react";

export interface PageProps {
  title: string;
  subtitle?: string;
  trail?: Array<{ label: string; href?: string }>;
  actions?: ReactNode;
  children: ReactNode;
}

/**
 * The canonical page wrapper, emitting the design system's page/page-head
 * vocabulary.
 *
 * This renders a div rather than <main>: the workspace shell already provides
 * the single main landmark, so the previous <main id="main-content"> here
 * produced a nested main and a duplicate id on every surface that used it.
 */
export function Page({ title, subtitle, trail, actions, children }: PageProps) {
  return (
    <div className="page">
      <header className="page-head">
        {trail && trail.length > 0 && (
          <nav className="breadcrumb" aria-label="Breadcrumb">
            {trail.map((item, index) => {
              const last = index === trail.length - 1;
              return (
                <React.Fragment key={`${item.label}-${index}`}>
                  {item.href && !last ? (
                    <a href={item.href}>{item.label}</a>
                  ) : (
                    <span aria-current="page">{item.label}</span>
                  )}
                  {!last && (
                    <span className="breadcrumb-sep" aria-hidden="true">
                      /
                    </span>
                  )}
                </React.Fragment>
              );
            })}
          </nav>
        )}
        <div className="page-head-row">
          <div>
            <h1 id="route-heading" tabIndex={-1}>
              {title}
            </h1>
            {subtitle && <p className="page-lede">{subtitle}</p>}
          </div>
          {actions && <div className="page-head-actions">{actions}</div>}
        </div>
      </header>
      {children}
    </div>
  );
}

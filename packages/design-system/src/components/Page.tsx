import React, { ReactNode } from "react";

export interface PageProps {
  title: string;
  subtitle?: string;
  trail?: Array<{ label: string; href?: string }>;
  actions?: ReactNode;
  children: ReactNode;
}

export function Page({ title, subtitle, trail, actions, children }: PageProps) {
  return (
    <main id="main-content" className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      {trail && trail.length > 0 && (
        <nav aria-label="Breadcrumb" className="mb-4">
          <ol className="flex items-center space-x-2 text-xs text-slate-500 dark:text-slate-400">
            {trail.map((item, idx) => (
              <li key={idx} className="flex items-center">
                {idx > 0 && <span className="mx-2 text-slate-300 dark:text-slate-600">/</span>}
                {item.href ? (
                  <a href={item.href} className="hover:text-slate-700 dark:hover:text-slate-200">
                    {item.label}
                  </a>
                ) : (
                  <span className="font-medium text-slate-700 dark:text-slate-200">{item.label}</span>
                )}
              </li>
            ))}
          </ol>
        </nav>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-6 border-b border-slate-200 dark:border-slate-800 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>}
        </div>
        {actions && <div className="mt-4 sm:mt-0 flex items-center space-x-3">{actions}</div>}
      </div>

      <div className="space-y-6">{children}</div>
    </main>
  );
}

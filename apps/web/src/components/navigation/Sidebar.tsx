import React from "react";

interface SidebarProps {
  orgSlug: string;
  activePath?: string;
}

export function Sidebar({ orgSlug, activePath = "projects" }: SidebarProps) {
  const links = [
    { label: "Clearance Projects", path: "projects", href: `/o/${orgSlug}/projects` },
    { label: "Team & Access", path: "team", href: `/o/${orgSlug}/team` },
    { label: "Workspace Settings", path: "settings", href: `/o/${orgSlug}/settings` },
  ];

  return (
    <aside
      aria-label="Organization sidebar"
      className="w-64 border-r border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50 p-4 space-y-1"
    >
      <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3 px-2">
        Workspace Menu
      </div>
      {links.map((link) => {
        const isActive = activePath === link.path;
        return (
          <a
            key={link.path}
            href={link.href}
            className={`block px-3 py-2 rounded-md text-sm font-medium transition-colors ${
              isActive
                ? "bg-blue-50 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300"
                : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-900 hover:text-slate-900 dark:hover:text-white"
            }`}
          >
            {link.label}
          </a>
        );
      })}
    </aside>
  );
}

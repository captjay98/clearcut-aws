import React from "react";
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { ThemeSwitcher } from "../theme/ThemeSwitcher";

interface AppShellProps {
  orgSlug?: string;
  projectId?: string;
  projectTitle?: string;
  userEmail?: string;
  userName?: string;
}

export function AppShell({
  orgSlug = "northlight",
  projectId,
  projectTitle,
  userEmail = "jamie@northlight.example",
  userName = "Jamie Park",
}: AppShellProps) {
  const routerState = useRouterState();
  const currentPath = routerState.location.pathname;

  const navLinks = [
    {
      label: "Clearance Projects",
      to: "/o/$orgSlug/projects",
      params: { orgSlug },
      active: currentPath.includes("/projects"),
      icon: "📋",
    },
    {
      label: "Team & Access",
      to: "/o/$orgSlug/team",
      params: { orgSlug },
      active: currentPath.includes("/team"),
      icon: "👥",
    },
    {
      label: "Trust Center",
      to: "/o/$orgSlug/trust",
      params: { orgSlug },
      active: currentPath.includes("/trust"),
      icon: "🛡️",
    },
    {
      label: "Workspace Settings",
      to: "/o/$orgSlug/settings",
      params: { orgSlug },
      active: currentPath.includes("/settings"),
      icon: "⚙️",
    },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100 font-sans">
      {/* Accessible Skip Link */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:px-4 focus:py-2 focus:bg-amber-500 focus:text-slate-950 focus:font-bold focus:rounded-md focus:shadow-lg focus:outline-none"
      >
        Skip to main content
      </a>

      {/* Top Header */}
      <header className="h-14 border-b border-slate-800 bg-slate-900/90 backdrop-blur px-4 flex items-center justify-between shrink-0 sticky top-0 z-40">
        <div className="flex items-center space-x-3">
          <Link
            to="/o/$orgSlug/projects"
            params={{ orgSlug }}
            className="flex items-center space-x-2 text-amber-500 hover:text-amber-400 font-black tracking-tight text-lg focus:outline-none focus:ring-2 focus:ring-amber-500 rounded"
          >
            <span className="text-xl">🎬</span>
            <span>ClearCut</span>
          </Link>

          <span className="text-slate-600 font-light">/</span>

          <span className="text-xs px-2 py-0.5 bg-slate-800 border border-slate-700 text-slate-300 rounded font-medium">
            {orgSlug}
          </span>

          {projectTitle && (
            <>
              <span className="text-slate-600 font-light">/</span>
              <span className="text-sm font-semibold text-slate-200 truncate max-w-[200px]">
                {projectTitle}
              </span>
            </>
          )}
        </div>

        <div className="flex items-center space-x-3">
          <ThemeSwitcher />

          {/* User Badge */}
          <div className="flex items-center space-x-2 pl-2 border-l border-slate-800">
            <div className="w-7 h-7 rounded-full bg-amber-600 flex items-center justify-center text-xs font-bold text-white uppercase shadow-sm">
              {userName.substring(0, 2)}
            </div>
            <div className="hidden sm:block text-left text-xs leading-tight">
              <div className="font-medium text-slate-200">{userName}</div>
              <div className="text-slate-500 truncate max-w-[120px]">{userEmail}</div>
            </div>
          </div>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Organization Sidebar Navigation */}
        <aside
          aria-label="Workspace navigation"
          className="w-60 border-r border-slate-800 bg-slate-900/40 shrink-0 hidden md:flex flex-col p-3 space-y-1"
        >
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-2 px-2.5">
            Workspace
          </div>

          <nav aria-label="Organization Navigation" className="space-y-1">
            {navLinks.map((link) => (
              <Link
                key={link.label}
                to={link.to}
                params={link.params}
                className={`flex items-center space-x-2.5 px-3 py-2 rounded-md text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-amber-500 ${
                  link.active
                    ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                }`}
              >
                <span aria-hidden="true" className="text-base">
                  {link.icon}
                </span>
                <span>{link.label}</span>
              </Link>
            ))}
          </nav>
        </aside>

        {/* Main Content Area */}
        <main
          id="main-content"
          tabIndex={-1}
          className="flex-1 flex flex-col overflow-y-auto focus:outline-none bg-slate-950 p-4 sm:p-6"
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}

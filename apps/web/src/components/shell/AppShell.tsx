import React, { useEffect, useState } from "react";
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";
import { ThemeSwitcher } from "../theme/ThemeSwitcher";
import { ShellProvider, useShell } from "./ShellContext";

interface NavItem {
  label: string;
  icon: string;
  to: string;
  /** Matched against the current path to set aria-current. */
  match: string;
}

interface NavGroup {
  label: string;
  links: readonly NavItem[];
}

/**
 * Mirrors NAV in the canonical mock (misc/clearcut-flow/assets/app.js): the rail
 * shows organization navigation at the org layer and swaps to project
 * navigation once inside a project. Labels and glyphs come from the mock's
 * ROUTES table so the vocabulary matches.
 *
 * The mock's "Prototype tools" group (sitemap, states) is intentionally absent:
 * it is instrumentation for the prototype, not product.
 */
const ORG_NAV: readonly NavGroup[] = [
  {
    label: "Organization",
    links: [
      { label: "Projects", icon: "▤", to: "/o/$orgSlug/projects", match: "/projects" },
      {
        label: "Notifications",
        icon: "◔",
        to: "/o/$orgSlug/notifications",
        match: "/notifications",
      },
      { label: "Team & roles", icon: "◉", to: "/o/$orgSlug/team", match: "/team" },
      { label: "Settings", icon: "⚙", to: "/o/$orgSlug/settings", match: "/settings" },
    ],
  },
  {
    label: "Trust & records",
    links: [
      { label: "AI trust", icon: "◐", to: "/o/$orgSlug/trust", match: "/trust" },
      { label: "Records", icon: "≡", to: "/o/$orgSlug/records", match: "/records" },
    ],
  },
];

const PROJECT_NAV: readonly NavGroup[] = [
  {
    label: "Project",
    links: [
      {
        label: "Overview",
        icon: "◈",
        to: "/o/$orgSlug/projects/$projectId",
        match: "@overview",
      },
      {
        label: "Screenplay",
        icon: "⌑",
        to: "/o/$orgSlug/projects/$projectId/workspace",
        match: "/workspace",
      },
      {
        label: "Flags",
        icon: "☰",
        to: "/o/$orgSlug/projects/$projectId/items",
        match: "/items",
      },
    ],
  },
  {
    label: "History & delivery",
    links: [
      {
        label: "Versions",
        icon: "⑂",
        to: "/o/$orgSlug/projects/$projectId/versions",
        match: "/versions",
      },
      {
        label: "Source watch",
        icon: "◉",
        to: "/o/$orgSlug/projects/$projectId/watch",
        match: "/watch",
      },
      {
        label: "Clearance report",
        icon: "◎",
        to: "/o/$orgSlug/projects/$projectId/report",
        match: "/report",
      },
    ],
  },
];

/** Project ids appear as the segment after /projects/, excluding /projects/new. */
function projectIdFrom(path: string): string | null {
  const match = /\/projects\/([^/]+)/.exec(path);
  if (!match || match[1] === "new") {
    return null;
  }
  return match[1];
}

function isCurrent(path: string, item: NavItem, projectId: string | null): boolean {
  if (item.match === "@overview") {
    // Overview is the project index, so it is current only when no child
    // segment follows the project id.
    return projectId !== null && new RegExp(`/projects/${projectId}/?$`).test(path);
  }
  return path.includes(item.match);
}

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) {
    return "CC";
  }
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

interface AppShellProps {
  orgSlug?: string;
  userName?: string;
  memberCount?: number;
}

export function AppShell(props: AppShellProps) {
  return (
    <ShellProvider>
      <AppShellInner {...props} />
    </ShellProvider>
  );
}

function AppShellInner({ orgSlug = "northlight", userName = "Jamie Park" }: AppShellProps) {
  const routerState = useRouterState();
  const currentPath = routerState.location.pathname;
  const projectId = projectIdFrom(currentPath);
  const inProject = projectId !== null;
  const { projectTitle, scriptPosition } = useShell();

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  // The mock's chip reads "<organization> · <n> members", so the shell resolves
  // both rather than falling back to the slug in the URL.
  const [orgName, setOrgName] = useState<string | null>(null);
  const [memberCount, setMemberCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadContext() {
      try {
        const orgs = await api.listOrganizations();
        if (!cancelled && orgs.ok) {
          const match = orgs.value.find((org) => org.slug === orgSlug || org.orgId === orgSlug);
          if (match) {
            setOrgName(match.name);
          }
        }
      } catch {
        // The chip shows the slug rather than inventing an organization name.
      }

      try {
        const members = await api.listOrganizationMembers({ params: { orgId: orgSlug } });
        if (!cancelled && members.ok) {
          setMemberCount(members.value.length);
        }
      } catch {
        // A missing count simply omits that half of the chip.
      }
    }
    loadContext();

    return () => {
      cancelled = true;
    };
  }, [orgSlug]);

  // The mock keys the shell's grid off body classes so the rail and the main
  // column stay in step, including when the rail collapses.
  useEffect(() => {
    document.body.classList.add("app-shell");
    return () => document.body.classList.remove("app-shell");
  }, []);

  useEffect(() => {
    document.body.classList.toggle("sidebar-collapsed", sidebarCollapsed);
  }, [sidebarCollapsed]);

  useEffect(() => {
    document.body.classList.toggle("dialog-open", drawerOpen);
    return () => document.body.classList.remove("dialog-open");
  }, [drawerOpen]);

  // A route change closes the drawer: it is navigation, so it must not survive
  // the navigation it triggered.
  useEffect(() => {
    setDrawerOpen(false);
  }, [currentPath]);

  const groups = inProject ? PROJECT_NAV : ORG_NAV;
  const params = inProject ? { orgSlug, projectId } : { orgSlug };

  const renderNav = () => (
    <>
      {inProject && (
        <div className="nav-group">
          <Link className="nav-link" to="/o/$orgSlug/projects" params={{ orgSlug }}>
            <span className="nav-icon" aria-hidden="true">
              ←
            </span>
            <span className="truncate">All projects</span>
          </Link>
        </div>
      )}
      {groups.map((group) => (
        <div className="nav-group" key={group.label}>
          <p className="nav-label">{group.label}</p>
          {group.links.map((item) => (
            <Link
              key={item.label}
              className="nav-link"
              to={item.to}
              params={params}
              data-label={item.label}
              aria-current={isCurrent(currentPath, item, projectId) ? "page" : undefined}
            >
              <span className="nav-icon" aria-hidden="true">
                {item.icon}
              </span>
              <span className="truncate">{item.label}</span>
            </Link>
          ))}
        </div>
      ))}
    </>
  );

  const mobilePrimary = inProject
    ? PROJECT_NAV.flatMap((group) => group.links).slice(0, 4)
    : ORG_NAV[0].links;

  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>

      <header className="app-header">
        <button
          className="icon-button is-bare nav-toggle"
          type="button"
          aria-label="Open navigation menu"
          aria-expanded={drawerOpen}
          aria-controls="mobile-drawer"
          onClick={() => setDrawerOpen(true)}
        >
          <span aria-hidden="true">☰</span>
        </button>
        <button
          className="icon-button is-bare rail-toggle"
          type="button"
          aria-expanded={!sidebarCollapsed}
          aria-controls="app-sidebar"
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={() => setSidebarCollapsed((value) => !value)}
        >
          <span aria-hidden="true">⇤</span>
        </button>

        <Link className="brand" to="/o/$orgSlug/projects" params={{ orgSlug }} aria-label="ClearCut projects">
          <span className="slate-mark" aria-hidden="true">
            <span>CC</span>
          </span>
          <span>ClearCut</span>
        </Link>

        <div className="org-chip" aria-label="Current context">
          {inProject ? (
            <strong>{projectTitle ?? "Project"}</strong>
          ) : (
            <>
              <strong>{orgName ?? orgSlug}</strong>
              {memberCount !== null && (
                <>
                  <span className="divider-dot" aria-hidden="true">
                    ·
                  </span>
                  <span className="muted small">
                    {memberCount} {memberCount === 1 ? "member" : "members"}
                  </span>
                </>
              )}
            </>
          )}
        </div>

        <div className="position-readout" aria-live="polite">
          {scriptPosition}
        </div>

        <div className="header-spacer" />

        <div className="header-actions">
          <Link className="button button-quiet" to="/o/$orgSlug/notifications" params={{ orgSlug }}>
            Inbox
          </Link>
          <ThemeSwitcher />
          <span className="avatar" aria-label={`Signed in as ${userName}`} title={userName}>
            {initialsOf(userName)}
          </span>
        </div>

        <span className="revision-bar" aria-hidden="true" />
      </header>

      <aside
        id="app-sidebar"
        className={`app-sidebar ${sidebarCollapsed ? "is-collapsed" : ""}`.trim()}
        aria-label="Primary navigation"
      >
        {renderNav()}
      </aside>

      <main id="main-content" tabIndex={-1}>
        <Outlet />
      </main>

      <nav className="mobile-nav" aria-label="Primary navigation">
        {mobilePrimary.map((item) => (
          <Link
            key={item.label}
            to={item.to}
            params={params}
            aria-current={isCurrent(currentPath, item, projectId) ? "page" : undefined}
          >
            <span className="nav-icon" aria-hidden="true">
              {item.icon}
            </span>
            <span className="truncate">{item.label.split(" ")[0]}</span>
          </Link>
        ))}
        <button type="button" onClick={() => setDrawerOpen(true)}>
          <span className="nav-icon" aria-hidden="true">
            ☰
          </span>
          <span>More</span>
        </button>
      </nav>

      <div id="mobile-drawer" className="mobile-drawer" data-open={drawerOpen ? "true" : "false"}>
        {drawerOpen && (
          <div className="drawer-panel" role="dialog" aria-modal="true" aria-label="Navigation menu">
            <div className="cluster-between gap-b-5">
              <strong>{inProject ? (projectTitle ?? "Project") : orgSlug}</strong>
              <button
                className="icon-button is-bare"
                type="button"
                aria-label="Close menu"
                onClick={() => setDrawerOpen(false)}
              >
                <span aria-hidden="true">✕</span>
              </button>
            </div>
            {renderNav()}
          </div>
        )}
      </div>
    </>
  );
}

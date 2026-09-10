import React, { useEffect, useState } from "react";
import { Link, Outlet, useNavigate, useRouterState } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";
import { ThemeSwitcher } from "../theme/ThemeSwitcher";
import { ShellProvider, useShell } from "./ShellContext";

import { revisionStock, revisionStockLabel } from "../../features/clearance/itemPresentation";

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

/**
 * Project ids appear as the segment after /projects/, excluding /projects/new.
 *
 * The parameter is named `pathname` deliberately. A contract guard rejects a
 * request-path option key appearing in any file that calls the generated
 * client, because a hand-built URL would bypass the client's typed params.
 */
function projectIdFrom(pathname: string): string | null {
  const match = /\/projects\/([^/]+)/.exec(pathname);
  if (!match || match[1] === "new") {
    return null;
  }
  return match[1];
}

function isCurrent(pathname: string, item: NavItem, projectId: string | null): boolean {
  if (item.match === "@overview") {
    // Overview is the project index, so it is current only when no child
    // segment follows the project id.
    return projectId !== null && new RegExp(`/projects/${projectId}/?$`).test(pathname);
  }
  return pathname.includes(item.match);
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

function AppShellInner({ orgSlug = "northlight", userName }: AppShellProps) {
  const routerState = useRouterState();
  const currentPath = routerState.location.pathname;
  const projectId = projectIdFrom(currentPath);
  const inProject = projectId !== null;
  const { projectTitle, scriptPosition } = useShell();
  const navigate = useNavigate();

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  // The mock's chip reads "<organization> · <n> members", so the shell resolves
  // both rather than falling back to the slug in the URL.
  const [orgName, setOrgName] = useState<string | null>(null);
  const [memberCount, setMemberCount] = useState<number | null>(null);
  // The avatar must name the authenticated account, never a mock identity.
  const [sessionLabel, setSessionLabel] = useState<string | null>(null);
  const [versionNumber, setVersionNumber] = useState<number | null>(null);
  const [flagCount, setFlagCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadContext() {
      try {
        const session = await api.getSessionContext();
        if (!cancelled && session.ok && session.value.email) {
          setSessionLabel(session.value.email);
        }
      } catch {
        // Fall through to the caller-supplied label if any.
      }

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

  useEffect(() => {
    let cancelled = false;
    if (!projectId) {
      setVersionNumber(null);
      return;
    }
    void (async () => {
      try {
        const result = await api.listProjectVersions({
          params: { orgId: orgSlug, projectId },
        });
        if (!cancelled && result.ok && result.value.length > 0) {
          const latest = result.value.reduce((best, row) =>
            (row.versionNumber ?? 0) > (best.versionNumber ?? 0) ? row : best,
          );
          setVersionNumber(latest.versionNumber ?? null);
        }
      } catch {
        // Version chip stays absent rather than inventing a stock colour.
      }
      try {
        const flags = await api.listClearanceItems({
          params: { orgId: orgSlug, projectId },
        });
        if (!cancelled && flags.ok) {
          setFlagCount(flags.value.length);
        }
      } catch {
        // Badge stays absent when the count is unavailable.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [orgSlug, projectId]);

  const displayName = sessionLabel ?? userName ?? "Signed-in user";

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
              {item.label === "Flags" && flagCount !== null && flagCount > 0 && (
                <span className="mono small muted" data-testid="flags-nav-count">
                  {flagCount}
                </span>
              )}
            </Link>
          ))}
        </div>
      ))}
    </>
  );

  const mobilePrimary = inProject
    ? PROJECT_NAV.flatMap((group) => group.links).slice(0, 4)
    : ORG_NAV[0].links;

  // Sign out revokes the current session, then routes to sign-in. The redirect
  // runs whether or not revocation succeeded: a stale session should never
  // strand the user inside the authenticated shell.
  const handleSignOut = async () => {
    if (signingOut) {
      return;
    }
    setSigningOut(true);
    try {
      await api.deleteCurrentSession();
    } catch {
      // A network failure still drops the user at sign-in below.
    } finally {
      navigate({ to: "/auth/sign-in" });
    }
  };

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
            <>
              <strong>{projectTitle ?? "Project"}</strong>
              {versionNumber !== null && (
                <>
                  <span className="divider-dot" aria-hidden="true">
                    ·
                  </span>
                  <span
                    className="small mono"
                    data-testid="revision-stock-chip"
                    title={revisionStockLabel(versionNumber)}
                  >
                    v{versionNumber} — {revisionStockLabel(versionNumber)}
                  </span>
                </>
              )}
            </>
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
          <span className="avatar" aria-label={`Signed in as ${displayName}`} title={displayName}>
            {initialsOf(displayName)}
          </span>
          <button
            className="button button-quiet"
            type="button"
            onClick={handleSignOut}
            disabled={signingOut}
          >
            {signingOut ? "Signing out…" : "Sign out"}
          </button>
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
            <div className="nav-group">
              <button
                className="button button-quiet"
                type="button"
                onClick={handleSignOut}
                disabled={signingOut}
              >
                {signingOut ? "Signing out…" : "Sign out"}
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

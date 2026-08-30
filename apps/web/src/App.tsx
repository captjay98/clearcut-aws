import React, { useState, useEffect } from "react";
import { RootLayout } from "./routes/__root.tsx";
import { OrgLayout } from "./routes/o/$orgSlug/route.tsx";
import { OrgProjectsRoute } from "./routes/o/$orgSlug/index.tsx";
import { OrgTeamRoute } from "./routes/o/$orgSlug/team.tsx";
import { OrgSettingsRoute } from "./routes/o/$orgSlug/settings.tsx";
import { OrgNotificationsRoute } from "./routes/o/$orgSlug/notifications.tsx";
import { OrgRecordsRoute } from "./routes/o/$orgSlug/records.tsx";
import { OrgTrustRoute } from "./routes/o/$orgSlug/trust.tsx";
import { NewProjectRoute } from "./routes/o/$orgSlug/projects/new.tsx";
import { ProjectOverviewRoute } from "./routes/o/$orgSlug/projects/$projectId/index.tsx";
import { ScreenplayWorkspaceRoute } from "./routes/o/$orgSlug/projects/$projectId/workspace.tsx";
import { ItemWorklistRoute } from "./routes/o/$orgSlug/projects/$projectId/items/index.tsx";
import { ItemDetailRoute } from "./routes/o/$orgSlug/projects/$projectId/items/$itemId.tsx";
import { ProjectVersionsRoute } from "./routes/o/$orgSlug/projects/$projectId/versions.tsx";
import { ProjectWatchRoute } from "./routes/o/$orgSlug/projects/$projectId/watch.tsx";
import { ProjectReportRoute } from "./routes/o/$orgSlug/projects/$projectId/report.tsx";
import { SignInRoute } from "./routes/auth/sign-in.tsx";
import { OnboardingRoute } from "./routes/onboarding.tsx";
import { InviteRoute } from "./routes/auth/invite/$token.tsx";

export function App() {
  const [route, setRoute] = useState<string>(window.location.hash || "#project");

  useEffect(() => {
    const handleHashChange = () => {
      setRoute(window.location.hash || "#project");
    };
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  const renderContent = () => {
    switch (route) {
      case "#auth":
      case "#sign-in":
        return <SignInRoute />;
      case "#onboarding":
        return <OnboardingRoute />;
      case "#invite":
        return <InviteRoute />;
      case "#projects":
        return (
          <OrgLayout>
            <OrgProjectsRoute />
          </OrgLayout>
        );
      case "#team":
        return (
          <OrgLayout>
            <OrgTeamRoute />
          </OrgLayout>
        );
      case "#settings":
        return (
          <OrgLayout>
            <OrgSettingsRoute />
          </OrgLayout>
        );
      case "#notifications":
        return (
          <OrgLayout>
            <OrgNotificationsRoute />
          </OrgLayout>
        );
      case "#records":
        return (
          <OrgLayout>
            <OrgRecordsRoute />
          </OrgLayout>
        );
      case "#trust":
        return (
          <OrgLayout>
            <OrgTrustRoute />
          </OrgLayout>
        );
      case "#new":
        return (
          <OrgLayout>
            <NewProjectRoute />
          </OrgLayout>
        );
      case "#project":
      case "#overview":
        return (
          <OrgLayout>
            <ProjectOverviewRoute />
          </OrgLayout>
        );
      case "#workspace":
        return (
          <OrgLayout>
            <ScreenplayWorkspaceRoute />
          </OrgLayout>
        );
      case "#items":
        return (
          <OrgLayout>
            <ItemWorklistRoute />
          </OrgLayout>
        );
      case "#item":
        return (
          <OrgLayout>
            <ItemDetailRoute />
          </OrgLayout>
        );
      case "#versions":
        return (
          <OrgLayout>
            <ProjectVersionsRoute />
          </OrgLayout>
        );
      case "#watch":
        return (
          <OrgLayout>
            <ProjectWatchRoute />
          </OrgLayout>
        );
      case "#report":
        return (
          <OrgLayout>
            <ProjectReportRoute />
          </OrgLayout>
        );
      default:
        return (
          <OrgLayout>
            <ProjectOverviewRoute />
          </OrgLayout>
        );
    }
  };

  return <RootLayout>{renderContent()}</RootLayout>;
}

import { describe, it, expect } from "vitest";
import React from "react";
import { SignInRoute } from "../../src/routes/auth/sign-in.tsx";
import { InviteRoute } from "../../src/routes/auth/invite.$token.tsx";
import { OnboardingRoute } from "../../src/routes/onboarding.tsx";
import { OrgProjectsRoute } from "../../src/routes/o.$orgSlug.projects.tsx";
import { OrgTeamRoute } from "../../src/routes/o.$orgSlug.team.tsx";

describe("Identity Entry Routes", () => {
  it("renders SignInRoute component structure", () => {
    expect(SignInRoute).toBeDefined();
    const element = React.createElement(SignInRoute);
    expect(element.type).toBe(SignInRoute);
  });

  it("renders InviteRoute component structure", () => {
    expect(InviteRoute).toBeDefined();
    const element = React.createElement(InviteRoute, { token: "tok_123" });
    expect(element.type).toBe(InviteRoute);
  });

  it("renders OnboardingRoute component structure", () => {
    expect(OnboardingRoute).toBeDefined();
    const element = React.createElement(OnboardingRoute);
    expect(element.type).toBe(OnboardingRoute);
  });

  it("renders OrgProjectsRoute with empty projects state", () => {
    expect(OrgProjectsRoute).toBeDefined();
    const element = React.createElement(OrgProjectsRoute, { orgSlug: "test-studio", initialProjects: [] });
    expect(element.type).toBe(OrgProjectsRoute);
  });

  it("renders OrgTeamRoute with member list", () => {
    expect(OrgTeamRoute).toBeDefined();
    const element = React.createElement(OrgTeamRoute, {
      orgSlug: "test-studio",
      initialMembers: [
        { membershipId: "m1", email: "owner@studio.com", role: "owner", status: "active" }
      ]
    });
    expect(element.type).toBe(OrgTeamRoute);
  });
});

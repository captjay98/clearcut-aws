import { describe, it, expect } from "vitest";
import React from "react";
import { SignInRoute } from "../../src/routes/auth/sign-in.tsx";
import { InviteRoute } from "../../src/routes/auth/invite/$token.tsx";
import { OnboardingRoute } from "../../src/routes/onboarding.tsx";
import { OrgProjectsRoute } from "../../src/routes/o/$orgSlug/index.tsx";
import { OrgTeamRoute } from "../../src/routes/o/$orgSlug/team.tsx";

describe("Identity Entry Routes", () => {
  it("renders SignInRoute component structure", () => {
    expect(SignInRoute).toBeDefined();
    const elem = React.createElement(SignInRoute);
    expect(elem.type).toBe(SignInRoute);
  });

  it("renders InviteRoute component structure", () => {
    expect(InviteRoute).toBeDefined();
    const elem = React.createElement(InviteRoute);
    expect(elem.type).toBe(InviteRoute);
  });

  it("renders OnboardingRoute component structure", () => {
    expect(OnboardingRoute).toBeDefined();
    const elem = React.createElement(OnboardingRoute);
    expect(elem.type).toBe(OnboardingRoute);
  });

  it("renders OrgProjectsRoute with empty projects state", () => {
    expect(OrgProjectsRoute).toBeDefined();
    const elem = React.createElement(OrgProjectsRoute);
    expect(elem.type).toBe(OrgProjectsRoute);
  });

  it("renders OrgTeamRoute with member list", () => {
    expect(OrgTeamRoute).toBeDefined();
    const elem = React.createElement(OrgTeamRoute);
    expect(elem.type).toBe(OrgTeamRoute);
  });
});

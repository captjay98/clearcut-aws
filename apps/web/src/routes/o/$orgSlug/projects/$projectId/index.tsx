import React from "react";
import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/")({
  beforeLoad: ({ params }) => {
    throw redirect({
      to: "/o/$orgSlug/projects/$projectId/workspace",
      params: { orgSlug: params.orgSlug, projectId: params.projectId },
    });
  },
  component: () => null,
});

export default Route;

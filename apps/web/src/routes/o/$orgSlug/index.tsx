import React from "react";
import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/o/$orgSlug/")({
  beforeLoad: ({ params }) => {
    throw redirect({
      to: "/o/$orgSlug/projects",
      params: { orgSlug: params.orgSlug },
    });
  },
  component: () => null,
});

export default Route;

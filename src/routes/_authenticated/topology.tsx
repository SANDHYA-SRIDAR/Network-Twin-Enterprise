import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/network/app-shell";
import { NetworkWorkspace } from "@/components/network/network-workspace";

export const Route = createFileRoute("/_authenticated/topology")({
  head: () => ({ meta: [{ title: "Topology Workspace | NetTransform AI" }, { name: "description", content: "Design, validate, and simulate enterprise network transformations." }, { property: "og:title", content: "Topology Workspace | NetTransform AI" }, { property: "og:description", content: "Design, validate, and simulate enterprise network transformations." }, { property: "og:type", content: "website" }, { name: "twitter:card", content: "summary_large_image" }] }),
  component: () => <AppShell><NetworkWorkspace /></AppShell>,
});
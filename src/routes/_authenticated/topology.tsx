import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/network/app-shell";
import { NetworkWorkspace } from "@/components/network/network-workspace";

export const Route = createFileRoute("/_authenticated/topology")({
  head: () => ({ meta: [{ title: "Topology Workspace | NexusTwin" }, { name: "description", content: "Design and synchronize your enterprise network digital twin." }, { property: "og:title", content: "Topology Workspace | NexusTwin" }, { property: "og:description", content: "Design and synchronize your enterprise network digital twin." }, { property: "og:type", content: "website" }, { name: "twitter:card", content: "summary_large_image" }] }),
  component: () => <AppShell><NetworkWorkspace /></AppShell>,
});
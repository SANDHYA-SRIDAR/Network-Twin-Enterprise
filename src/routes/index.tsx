import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { supabase } from "@/integrations/supabase/custom-client";

// No head() here: the home route inherits title/description/og/twitter from
// __root.tsx, and ships no og:image so serve-time hosting can inject the
// project's social preview (explicit og:image or latest screenshot).
export const Route = createFileRoute("/")({
  head: () => ({ meta: [
    { title: "NetTransform AI | Enterprise Network Simulator" },
    { name: "description", content: "Simulate, transform, modernize, and optimize enterprise networks." },
    { property: "og:title", content: "NetTransform AI | Enterprise Network Simulator" },
    { property: "og:description", content: "Model, synchronize, and optimize enterprise network topologies." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ]}),
  component: Index,
});

// IMPORTANT: Replace this placeholder. See ./README.md for routing conventions.
function Index() {
  const navigate = useNavigate();
  useEffect(() => {
    void supabase.auth.getUser().then(({ data }) => {
      void navigate({ to: data.user ? "/topology" : "/auth", replace: true });
    });
  }, [navigate]);
  return <div className="grid min-h-screen place-items-center bg-background text-sm text-muted-foreground">Loading NetTransform AI…</div>;
}

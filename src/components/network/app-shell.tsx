import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { Bot, CloudCog, CloudUpload, Gauge, LogOut, Moon, Network, RotateCcw, Sun } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { supabase } from "@/integrations/supabase/custom-client";

export function AppShell({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const onTopology = useRouterState({ select: state => state.location.pathname === "/topology" });
  const [dark, setDark] = useState(true);
  const [assistantOpen, setAssistantOpen] = useState(true);
  const [telemetryOpen, setTelemetryOpen] = useState(true);
  useEffect(() => {
    const stored = localStorage.getItem("nexustwin-theme");
    const next = stored ? stored === "dark" : true;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
  }, []);
  useEffect(() => {
    const onPanelState = (event: Event) => { const detail = (event as CustomEvent<{ assistantOpen?: boolean; telemetryOpen?: boolean }>).detail; if (typeof detail.assistantOpen === "boolean") setAssistantOpen(detail.assistantOpen); if (typeof detail.telemetryOpen === "boolean") setTelemetryOpen(detail.telemetryOpen); };
    window.addEventListener("nettransform:panel-state", onPanelState);
    return () => { window.removeEventListener("nettransform:panel-state", onPanelState); };
  }, []);
  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("nexustwin-theme", next ? "dark" : "light");
  };
  const logout = async () => {
    await supabase.auth.signOut();
    void navigate({ to: "/auth", replace: true });
  };
  return <div className="flex h-screen flex-col overflow-hidden bg-background">
    <header className="z-30 flex h-14 shrink-0 items-center justify-between border-b bg-card px-3 sm:px-5">
      <div className="flex items-center gap-3">
        <div className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground"><Network className="size-4" /></div>
        <div><div className="text-sm font-bold">NetTransform AI</div><div className="hidden text-[10px] font-mono uppercase text-muted-foreground sm:block">AI network transformation</div></div>
      </div>
      <nav className="min-w-0 flex items-center justify-end gap-1 overflow-x-auto">
        <Button asChild variant="ghost" size="sm"><Link to="/topology"><Network /> Topology</Link></Button>
        <Button asChild variant="ghost" size="sm"><Link to="/scenarios"><CloudCog /> Scenario Studio</Link></Button>
        <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex"><Link to="/recommendations"><CloudCog /> Recommendations</Link></Button>
        {onTopology && <>
          <Button variant={assistantOpen ? "secondary" : "ghost"} size="sm" onClick={() => { setAssistantOpen(current => !current); window.dispatchEvent(new Event("nettransform:toggle-assistant")); }} title="Toggle AI Assistant"><Bot /> <span className="hidden lg:inline">AI Assistant</span></Button>
          <Button variant={telemetryOpen ? "secondary" : "ghost"} size="sm" onClick={() => { setTelemetryOpen(current => !current); window.dispatchEvent(new Event("nettransform:toggle-telemetry")); }} title="Toggle simulated network monitor"><Gauge /> <span className="hidden lg:inline">Monitor</span></Button>
        </>}
        {onTopology && <Button variant="outline" size="sm" onClick={() => window.dispatchEvent(new Event("nexustwin:restore-working-topology"))} title="Restore the screenshot topology"><RotateCcw /> <span className="hidden xl:inline">Restore working topology</span></Button>}
        {onTopology && <Button size="sm" onClick={() => window.dispatchEvent(new Event("nexustwin:save"))}><CloudUpload /> <span className="hidden sm:inline">Save Topology</span></Button>}
        <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={dark ? "Use light theme" : "Use dark theme"}>{dark ? <Sun /> : <Moon />}</Button>
        <Button variant="ghost" size="icon" onClick={logout} aria-label="Logout"><LogOut /></Button>
      </nav>
    </header>
    {children}
  </div>;
}

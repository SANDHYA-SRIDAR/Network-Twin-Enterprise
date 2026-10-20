import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Eye, EyeOff, Network, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { supabase } from "@/integrations/supabase/custom-client";

export const Route = createFileRoute("/auth")({
  head: () => ({ meta: [
    { title: "Sign in | NexusTwin" }, { name: "description", content: "Secure access to your NexusTwin network workspace." },
    { property: "og:title", content: "Sign in | NexusTwin" }, { property: "og:description", content: "Secure access to your NexusTwin network workspace." },
    { property: "og:type", content: "website" }, { name: "twitter:card", content: "summary" },
  ]}),
  component: AuthPage,
});

function AuthPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy(true); setMessage("");
    const form = new FormData(event.currentTarget); const email = String(form.get("email")); const password = String(form.get("password"));
    const result = mode === "register"
      ? await supabase.auth.signUp({ email, password, options: { data: { display_name: String(form.get("name")) }, emailRedirectTo: window.location.origin } })
      : await supabase.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (result.error) return setMessage(result.error.message);
    if (mode === "register" && !result.data.session) return setMessage("Check your inbox to confirm your account.");
    void navigate({ to: "/topology", replace: true });
  };
  const google = async () => {
    setBusy(true);
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin, queryParams: { prompt: "select_account" } },
    });
    if (error) { setMessage(error.message); setBusy(false); }
  };
  const forgot = async () => {
    const email = window.prompt("Enter your account email"); if (!email) return;
    const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: `${window.location.origin}/reset-password` });
    setMessage(error?.message ?? "Password reset instructions sent.");
  };
  return <main className="grid min-h-screen bg-background lg:grid-cols-[1.1fr_.9fr]">
    <section className="relative hidden overflow-hidden border-r bg-primary p-12 text-primary-foreground lg:flex lg:flex-col lg:justify-between">
      <div className="absolute inset-0 opacity-15 grid-surface" />
      <div className="relative flex items-center gap-3"><div className="grid size-10 place-items-center rounded-md border border-primary-foreground/20"><Network /></div><span className="text-xl font-bold">NexusTwin</span></div>
      <div className="relative max-w-xl"><p className="mb-5 font-mono text-xs uppercase opacity-70">Enterprise network intelligence</p><h1 className="text-5xl font-semibold leading-tight">See every path.<br/>Simulate every change.</h1><p className="mt-6 max-w-md text-base opacity-75">A synchronized digital twin for designing, testing, and optimizing critical infrastructure.</p></div>
      <div className="relative flex items-center gap-3 text-sm opacity-75"><ShieldCheck className="size-4" /> Encrypted workspace · Realtime state · Isolated access</div>
    </section>
    <section className="flex items-center justify-center p-6"><div className="w-full max-w-md">
      <div className="mb-8 lg:hidden"><Network className="mb-3 text-primary"/><h1 className="text-2xl font-bold">NexusTwin</h1></div>
      <p className="font-mono text-xs uppercase text-primary">Secure access</p><h2 className="mt-2 text-3xl font-semibold">{mode === "login" ? "Welcome back" : "Create your workspace"}</h2><p className="mt-2 text-sm text-muted-foreground">{mode === "login" ? "Resume your network operations workspace." : "Start building your enterprise digital twin."}</p>
      <form className="mt-8 space-y-4" onSubmit={submit}>
        {mode === "register" && <div className="space-y-2"><Label htmlFor="name">Display name</Label><Input id="name" name="name" required placeholder="Alex Morgan" /></div>}
        <div className="space-y-2"><Label htmlFor="email">Work email</Label><Input id="email" name="email" type="email" required placeholder="alex@company.com" /></div>
        <div className="space-y-2"><div className="flex justify-between"><Label htmlFor="password">Password</Label>{mode === "login" && <button type="button" onClick={forgot} className="text-xs text-primary">Forgot password?</button>}</div><div className="relative"><Input id="password" name="password" type={show ? "text" : "password"} required minLength={8} className="pr-10"/><Button type="button" variant="ghost" size="icon" onClick={() => setShow(!show)} className="absolute right-0 top-0" aria-label="Show password">{show ? <EyeOff/> : <Eye/>}</Button></div></div>
        <div className="flex items-center gap-2"><Checkbox id="remember" defaultChecked/><Label htmlFor="remember" className="text-xs font-normal text-muted-foreground">Keep me signed in until I log out</Label></div>
        {message && <p className="rounded-md border bg-muted p-3 text-sm" role="status">{message}</p>}
        <Button className="w-full" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</Button>
      </form>
      <div className="my-5 flex items-center gap-3 text-xs text-muted-foreground"><div className="h-px flex-1 bg-border"/>OR<div className="h-px flex-1 bg-border"/></div>
      <Button variant="outline" className="w-full" onClick={google} disabled={busy}><span className="font-bold text-primary">G</span> Continue with Google</Button>
      <p className="mt-6 text-center text-sm text-muted-foreground">{mode === "login" ? "New to NexusTwin?" : "Already have an account?"} <button className="font-semibold text-primary" onClick={() => { setMode(mode === "login" ? "register" : "login"); setMessage(""); }}>{mode === "login" ? "Create account" : "Sign in"}</button></p>
    </div></section>
  </main>;
}

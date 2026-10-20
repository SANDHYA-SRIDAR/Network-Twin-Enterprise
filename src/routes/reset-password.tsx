import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { supabase } from "@/integrations/supabase/custom-client";

export const Route = createFileRoute("/reset-password")({
  head: () => ({ meta: [{ title: "Reset password | NetTransform AI" }, { name: "description", content: "Set a new NetTransform AI account password." }, { property: "og:title", content: "Reset password | NetTransform AI" }, { property: "og:description", content: "Set a new NetTransform AI account password." }, { property: "og:type", content: "website" }, { name: "twitter:card", content: "summary" }] }),
  component: ResetPassword,
});
function ResetPassword() {
  const navigate = useNavigate(); const [message, setMessage] = useState("");
  const submit = async (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const password = String(new FormData(e.currentTarget).get("password")); const { error } = await supabase.auth.updateUser({ password }); if (error) setMessage(error.message); else void navigate({ to: "/topology", replace: true }); };
  return <main className="grid min-h-screen place-items-center bg-background p-6"><form onSubmit={submit} className="w-full max-w-sm space-y-5 border bg-card p-7 shadow-xl"><div><h1 className="text-2xl font-semibold">Set a new password</h1><p className="mt-2 text-sm text-muted-foreground">Choose at least eight characters.</p></div><div className="space-y-2"><Label htmlFor="password">New password</Label><Input id="password" name="password" type="password" minLength={8} required /></div>{message && <p className="text-sm text-destructive">{message}</p>}<Button className="w-full">Update password</Button></form></main>;
}
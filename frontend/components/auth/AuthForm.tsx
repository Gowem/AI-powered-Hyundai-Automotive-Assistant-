"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";

import { PasswordInput } from "@/components/auth/PasswordInput";
import { Brand, Disclaimer } from "@/components/layout/Brand";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";

const email = z.string().trim().min(1, "Email is required").email("Enter a valid email address");
const loginSchema = z.object({ email, password: z.string().min(1, "Password is required") });
const registerSchema = z.object({
  full_name: z.string().trim().max(120, "Name is too long").optional(),
  email,
  password: z
    .string()
    .min(8, "At least 8 characters")
    .max(128, "At most 128 characters")
    .regex(/[A-Za-z]/, "Include at least one letter")
    .regex(/\d/, "Include at least one number"),
});

type Errors = Partial<Record<"email" | "password" | "full_name" | "form", string>>;

function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/chat";
}

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const [errors, setErrors] = useState<Errors>({});
  const [loading, setLoading] = useState(false);
  const isLogin = mode === "login";
  const showDemo = isLogin && process.env.NEXT_PUBLIC_SHOW_DEMO_HINT !== "false";
  const demoEmail = process.env.NEXT_PUBLIC_DEMO_EMAIL ?? "demo@hyundai-assistant.app";
  const demoPassword = process.env.NEXT_PUBLIC_DEMO_PASSWORD ?? "Demo1234";

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const raw = Object.fromEntries(form.entries());
    const parsed = (isLogin ? loginSchema : registerSchema).safeParse(raw);
    if (!parsed.success) {
      const errs: Errors = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0] as keyof Errors;
        errs[key] ??= issue.message;
      }
      setErrors(errs);
      return;
    }
    setErrors({});
    setLoading(true);
    try {
      const user = await api<User>(isLogin ? "/api/auth/login" : "/api/auth/register", {
        method: "POST",
        json: parsed.data,
      });
      qc.setQueryData(["me"], user);
      toast.success(isLogin ? "Welcome back" : "Account created");
      router.replace(safeNext(params.get("next")));
      router.refresh();
    } catch (err) {
      setErrors({ form: err instanceof Error ? err.message : "Something went wrong" });
    } finally {
      setLoading(false);
    }
  }

  function fillDemo() {
    const f = document.getElementById("auth-form") as HTMLFormElement | null;
    if (!f) return;
    (f.elements.namedItem("email") as HTMLInputElement).value = demoEmail;
    (f.elements.namedItem("password") as HTMLInputElement).value = demoPassword;
  }

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 bg-gradient-to-b from-[#002c5f]/[0.06] to-transparent p-4">
      <Brand />
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">{isLogin ? "Sign in" : "Create an account"}</CardTitle>
          <CardDescription>
            {isLogin
              ? "Chat with an AI consultant grounded in Hyundai brochures."
              : "Use your email and a password with at least 8 characters, one letter and one number."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form id="auth-form" onSubmit={onSubmit} className="grid gap-4" noValidate>
            {!isLogin && (
              <div className="grid gap-2">
                <Label htmlFor="full_name">Name (optional)</Label>
                <Input id="full_name" name="full_name" autoComplete="name" aria-invalid={!!errors.full_name} />
                {errors.full_name && <p className="text-destructive text-xs">{errors.full_name}</p>}
              </div>
            )}
            <div className="grid gap-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="you@example.com"
                aria-invalid={!!errors.email}
                aria-describedby={errors.email ? "email-error" : undefined}
              />
              {errors.email && (
                <p id="email-error" className="text-destructive text-xs">
                  {errors.email}
                </p>
              )}
            </div>
            <div className="grid gap-2">
              <Label htmlFor="password">Password</Label>
              <PasswordInput
                id="password"
                name="password"
                autoComplete={isLogin ? "current-password" : "new-password"}
                aria-invalid={!!errors.password}
                aria-describedby={errors.password ? "password-error" : undefined}
              />
              {errors.password && (
                <p id="password-error" className="text-destructive text-xs">
                  {errors.password}
                </p>
              )}
            </div>
            {errors.form && (
              <p role="alert" className="bg-destructive/10 text-destructive rounded-md px-3 py-2 text-sm">
                {errors.form}
              </p>
            )}
            <Button type="submit" disabled={loading} className="w-full">
              {loading && <Loader2 className="animate-spin" />}
              {isLogin ? "Sign in" : "Create account"}
            </Button>
          </form>
          {showDemo && (
            <div className="bg-muted/60 mt-4 rounded-lg border border-dashed p-3 text-xs">
              <p className="font-medium">Reviewer demo account</p>
              <p className="text-muted-foreground mt-1 font-mono break-all">
                {demoEmail} / {demoPassword}
              </p>
              <Button type="button" variant="link" size="sm" className="mt-1 h-auto p-0 text-xs" onClick={fillDemo}>
                Fill in demo credentials
              </Button>
            </div>
          )}
          <p className="text-muted-foreground mt-5 text-center text-sm">
            {isLogin ? "New here? " : "Already have an account? "}
            <Link
              href={isLogin ? "/register" : "/login"}
              className="text-primary font-medium underline-offset-4 hover:underline"
            >
              {isLogin ? "Create an account" : "Sign in"}
            </Link>
          </p>
        </CardContent>
      </Card>
      <Disclaimer className="max-w-sm text-center" />
    </main>
  );
}

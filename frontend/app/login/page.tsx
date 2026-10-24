"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, fetchConfig, PublicConfig, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [config, setConfig] = useState<PublicConfig | null>(null);

  // links from the landing page open this page ready for sign-up or the demo
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("mode") === "register") setMode("register");
    fetchConfig().then(setConfig).catch(() => {});
  }, []);

  const signupsClosed = config !== null && !config.registration_open;

  async function login(emailValue: string, passwordValue: string) {
    // FastAPI's OAuth2 login expects a form with "username" and "password"
    const { access_token } = await api<{ access_token: string }>("/auth/login", {
      method: "POST",
      form: { username: emailValue, password: passwordValue },
    });
    setToken(access_token);
    router.push("/dashboard");
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "register") {
        await api("/auth/register", {
          method: "POST",
          body: { email, full_name: fullName, password },
        });
      }
      await login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server. Is the API running?");
      setBusy(false);
    }
  }

  const input =
    "mt-1 w-full rounded-lg border border-line bg-page px-3 py-2 text-sm outline-none focus:border-accent";

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <Link href="/" className="text-2xl font-semibold">
            Spend<span className="text-accent">Sense</span>
          </Link>
          <p className="mt-1 text-sm text-muted">Your spending, tracked live.</p>
        </div>

        <form onSubmit={submit} className="space-y-4 rounded-2xl border border-line bg-surface p-6">
          <h2 className="font-medium">{mode === "login" ? "Log in" : "Create your account"}</h2>

          {mode === "register" && signupsClosed ? (
            <p className="text-sm text-muted">New sign-ups are paused right now. Please check back soon.</p>
          ) : (
            <>
              {mode === "register" && (
                <label className="block text-xs text-muted">
                  Full name
                  <input className={input} value={fullName} onChange={(e) => setFullName(e.target.value)} required />
                </label>
              )}
              <label className="block text-xs text-muted">
                Email
                <input
                  className={input}
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </label>
              <label className="block text-xs text-muted">
                Password
                <input
                  className={input}
                  type="password"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  minLength={mode === "register" ? 8 : undefined}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                {mode === "register" && <span className="mt-1 block">At least 8 characters. Avoid common passwords.</span>}
              </label>

              {mode === "register" && (
                <label className="flex items-start gap-2 text-xs text-muted">
                  <input
                    type="checkbox"
                    checked={agreed}
                    onChange={(e) => setAgreed(e.target.checked)}
                    required
                    className="mt-0.5"
                  />
                  <span>
                    I have read the{" "}
                    <Link href="/privacy" target="_blank" className="text-accent hover:underline">
                      privacy notice
                    </Link>{" "}
                    and understand this is a small student project: my payments&apos; date, shop, amount and category will
                    be stored until I delete my account.
                  </span>
                </label>
              )}

              {error && <p className="text-sm text-danger">{error}</p>}

              <button
                disabled={busy}
                className="w-full rounded-lg bg-accent py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-60"
              >
                {busy ? "Please wait…" : mode === "login" ? "Log in" : "Sign up"}
              </button>
            </>
          )}

          <p className="text-center text-sm text-muted">
            {mode === "login" ? "New here?" : "Already have an account?"}{" "}
            <button
              type="button"
              className="font-medium text-accent hover:underline"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError("");
              }}
            >
              {mode === "login" ? "Create an account" : "Log in"}
            </button>
          </p>
        </form>

        {config && (
          <button
            type="button"
            onClick={() => {
              setMode("login");
              setEmail(config.demo_email);
              setPassword("demo12345");
            }}
            className="mt-4 w-full text-center text-xs text-muted hover:text-ink"
          >
            Just looking? Fill in the demo account (sample data)
          </button>
        )}
        <p className="mt-3 text-center text-xs text-muted">
          <Link href="/privacy" className="hover:text-ink">
            Privacy notice
          </Link>
        </p>
      </div>
    </main>
  );
}

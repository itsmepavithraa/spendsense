"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api, ApiError, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

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
          <h1 className="text-2xl font-semibold">
            Spend<span className="text-accent">Sense</span>
          </h1>
          <p className="mt-1 text-sm text-muted">Your spending, tracked live.</p>
        </div>

        <form onSubmit={submit} className="space-y-4 rounded-2xl border border-line bg-surface p-6">
          <h2 className="font-medium">{mode === "login" ? "Log in" : "Create your account"}</h2>

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
          </label>

          {error && <p className="text-sm text-danger">{error}</p>}

          <button
            disabled={busy}
            className="w-full rounded-lg bg-accent py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-60"
          >
            {busy ? "Please wait…" : mode === "login" ? "Log in" : "Sign up"}
          </button>

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

        <button
          type="button"
          onClick={() => {
            setMode("login");
            setEmail("demo@spendsense.com");
            setPassword("demo12345");
          }}
          className="mt-4 w-full text-center text-xs text-muted hover:text-ink"
        >
          Fill in the demo account
        </button>
      </div>
    </main>
  );
}

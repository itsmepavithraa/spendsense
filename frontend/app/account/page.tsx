"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, clearToken, downloadMyData, getToken, User } from "@/lib/api";

export default function AccountPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [message, setMessage] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api<User>("/auth/me")
      .then(setUser)
      .catch(() => {
        clearToken();
        router.replace("/login");
      });
  }, [router]);

  async function download() {
    setMessage("");
    try {
      await downloadMyData();
      setMessage("Your data was downloaded as spendsense-my-data.json.");
    } catch {
      setMessage("Could not download your data. Please try again.");
    }
  }

  async function deleteAccount(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api("/auth/delete-account", { method: "POST", body: { password } });
      clearToken();
      router.replace("/?deleted=1");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete the account.");
      setBusy(false);
    }
  }

  if (!user) return <p className="p-8 text-center text-muted">Loading…</p>;

  const card = "rounded-2xl border border-line bg-surface p-5";
  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <Link href="/dashboard" className="text-sm text-muted hover:text-ink">
        ← Dashboard
      </Link>
      <h1 className="mt-2 text-xl font-semibold">Account</h1>
      <p className="mt-1 text-sm text-muted">
        {user.full_name} · {user.email}
      </p>

      <section className={`${card} mt-5`}>
        <h2 className="text-sm font-medium">Download my data</h2>
        <p className="mt-1 text-sm text-muted">
          Everything SpendSense stores about you (profile, transactions, category corrections) in one JSON file.
        </p>
        <button onClick={download} className="mt-3 rounded-lg border border-line px-4 py-2 text-sm hover:border-accent">
          Download my data
        </button>
        {message && <p className="mt-2 text-sm text-good">{message}</p>}
      </section>

      <section className={`${card} mt-4 border-danger/40`}>
        <h2 className="text-sm font-medium text-danger">Delete my account</h2>
        <p className="mt-1 text-sm text-muted">
          Permanently erases your account and every transaction, correction and payment record. This cannot be
          undone. Consider downloading your data first.
        </p>
        {!confirming ? (
          <button
            onClick={() => setConfirming(true)}
            className="mt-3 rounded-lg border border-danger px-4 py-2 text-sm text-danger hover:bg-danger/10"
          >
            Delete my account…
          </button>
        ) : (
          <form onSubmit={deleteAccount} className="mt-3 space-y-3">
            <label className="block text-xs text-muted">
              Type your password to confirm
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="mt-1 w-full rounded-lg border border-line bg-page px-3 py-2 text-sm outline-none focus:border-danger"
              />
            </label>
            {error && <p className="text-sm text-danger">{error}</p>}
            <div className="flex gap-2">
              <button
                disabled={busy}
                className="rounded-lg bg-danger px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-60"
              >
                {busy ? "Deleting…" : "Yes, delete everything"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setConfirming(false);
                  setPassword("");
                  setError("");
                }}
                className="rounded-lg border border-line px-4 py-2 text-sm"
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}

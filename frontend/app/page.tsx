"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchConfig, getToken, PublicConfig } from "@/lib/api";

const STEPS = [
  { title: "1. Export your statement", text: "Download the CSV statement from your bank's net banking. (PDF isn't supported.)" },
  { title: "2. Upload it here", text: "SpendSense reads the columns, cleans the shop names and sorts spending into categories." },
  { title: "3. See where it goes", text: "Charts, a plain-words summary and specific tips with an estimate of what you could save each month." },
];

export default function Home() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [deleted, setDeleted] = useState(false);

  useEffect(() => {
    setDeleted(new URLSearchParams(window.location.search).get("deleted") === "1");
    if (getToken()) {
      router.replace("/dashboard"); // already signed in: straight to the app
      return;
    }
    setReady(true);
    fetchConfig().then(setConfig).catch(() => {});
  }, [router]);

  if (!ready) return null;
  const closed = config !== null && !config.registration_open;

  return (
    <main className="mx-auto max-w-4xl px-4 py-12">
      <nav className="mb-16 flex items-center justify-between">
        <span className="text-xl font-semibold">
          Spend<span className="text-accent">Sense</span>
        </span>
        <Link href="/login" className="text-sm text-muted hover:text-ink">
          Log in
        </Link>
      </nav>

      {deleted && (
        <p className="mb-8 rounded-lg border border-good/40 px-4 py-3 text-center text-sm text-good">
          Your account and all its data have been deleted.
        </p>
      )}

      <section className="text-center">
        <h1 className="text-3xl font-semibold leading-tight sm:text-5xl">
          Upload your bank statement.
          <br />
          <span className="text-accent">See where your money goes.</span>
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-muted">
          Get a clear picture of your spending and practical ideas for saving, in charts and plain words. Free to use,
          and you can delete everything with one click.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          {closed ? (
            <p className="rounded-lg border border-line px-4 py-2 text-sm text-muted">
              New sign-ups are paused right now. Please check back soon.
            </p>
          ) : (
            <Link href="/login?mode=register" className="rounded-lg bg-accent px-5 py-3 text-sm font-medium text-white hover:opacity-90">
              Create a free account
            </Link>
          )}
          <Link href="/login?demo=1" className="rounded-lg border border-line px-5 py-3 text-sm hover:border-accent">
            Try the demo (sample data)
          </Link>
        </div>
      </section>

      <section className="mt-16 grid gap-4 sm:grid-cols-3">
        {STEPS.map((s) => (
          <div key={s.title} className="rounded-2xl border border-line bg-surface p-5">
            <h2 className="font-medium">{s.title}</h2>
            <p className="mt-2 text-sm text-muted">{s.text}</p>
          </div>
        ))}
      </section>

      <section className="mt-12 rounded-2xl border border-line bg-surface p-6">
        <h2 className="font-medium">Your data, your control</h2>
        <ul className="mt-3 space-y-2 text-sm text-muted">
          <li>• Only the date, shop name, amount and category of each payment are stored. Your bank login, account number and the original file are not.</li>
          <li>• Download all your data or permanently delete your account any time from the Account page.</li>
          <li>• No ads, no selling data, no third-party trackers.</li>
          <li>
            • This is a student-built project, not a bank-grade service. Please read the{" "}
            <Link href="/privacy" className="text-accent hover:underline">
              privacy notice
            </Link>{" "}
            before uploading real statements.
          </li>
        </ul>
      </section>

      <footer className="mt-12 flex flex-wrap justify-center gap-4 text-xs text-muted">
        <Link href="/privacy" className="hover:text-ink">Privacy</Link>
        <a href="https://github.com/itsmepavithraa/spendsense" className="hover:text-ink">Source code</a>
      </footer>
    </main>
  );
}

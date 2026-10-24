"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import InsightsView, { insightsToText } from "@/components/InsightsView";
import { api, ApiError, clearToken, getToken, Insights } from "@/lib/api";

const PERIODS = [
  { label: "Last 30 days", days: 30 },
  { label: "Last 60 days", days: 60 },
  { label: "Last 90 days", days: 90 },
  { label: "All time", days: 0 },
];

export default function InsightsPage() {
  const router = useRouter();
  const [days, setDays] = useState(30);
  const [data, setData] = useState<Insights | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(
    (windowDays: number) => {
      if (!getToken()) {
        router.replace("/login");
        return;
      }
      setError("");
      api<Insights>(`/analytics/insights?days=${windowDays}`)
        .then(setData)
        .catch((err) => {
          if (err instanceof ApiError && err.status === 401) {
            clearToken();
            router.replace("/login");
          } else {
            setError("Could not load your insights. Is the API running?");
          }
        });
    },
    [router],
  );

  useEffect(() => load(days), [days, load]);

  function downloadText() {
    if (!data) return;
    const blob = new Blob([insightsToText(data)], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `spendsense-report-${data.period.to ?? "today"}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link href="/dashboard" className="no-print text-sm text-muted hover:text-ink">
            ← Dashboard
          </Link>
          <h1 className="mt-1 text-xl font-semibold">
            Spend<span className="text-accent">Sense</span> <span className="font-normal text-muted">· Spending insights</span>
          </h1>
        </div>
        <div className="no-print flex flex-wrap items-center gap-2">
          <select
            aria-label="Period"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm outline-none focus:border-accent"
          >
            {PERIODS.map((p) => (
              <option key={p.days} value={p.days}>
                {p.label}
              </option>
            ))}
          </select>
          <button
            onClick={() => window.print()}
            disabled={!data}
            className="rounded-lg border border-line px-3 py-1.5 text-sm transition hover:border-accent disabled:opacity-50"
          >
            Print / Save as PDF
          </button>
          <button
            onClick={downloadText}
            disabled={!data}
            className="rounded-lg border border-line px-3 py-1.5 text-sm transition hover:border-accent disabled:opacity-50"
          >
            Download as text
          </button>
        </div>
      </header>

      {error && <p className="text-danger">{error}</p>}
      {!error && !data && <p className="text-muted">Working out your insights…</p>}
      {data && <InsightsView data={data} />}
    </div>
  );
}

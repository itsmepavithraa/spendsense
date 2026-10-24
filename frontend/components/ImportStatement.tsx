"use client";

import Link from "next/link";
import { ChangeEvent, useRef, useState } from "react";
import { api, ApiError, categoryColor, formatINRExact, ImportResult } from "@/lib/api";

const MAX_BYTES = 2 * 1024 * 1024;

interface Props {
  onImported: (result: ImportResult) => void;
  demo?: boolean; // the shared demo account: upload the sample file, not a real statement
}

// Upload a bank statement CSV. The server does the work; this shows exactly what happened.
export default function ImportStatement({ onImported, demo = false }: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);

  async function choose(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // lets the same file be picked again later
    if (!file) return;
    setError("");
    setResult(null);
    if (file.size > MAX_BYTES) {
      setError("That file is over 2 MB. Export a shorter date range from your bank.");
      return;
    }
    setBusy(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const summary = await api<ImportResult>("/transactions/import", { method: "POST", formData });
      setResult(summary);
      onImported(summary);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not upload the file. Is the API running?");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="p-5">
      <div className="flex flex-wrap items-center gap-3">
        <input ref={fileInput} type="file" accept=".csv,text/csv" onChange={choose} className="hidden" />
        <button
          onClick={() => fileInput.current?.click()}
          disabled={busy}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-60"
        >
          {busy ? "Importing…" : "Choose a CSV file"}
        </button>
        <a href="/sample-statement.csv" download className="text-sm text-accent hover:underline">
          Download a sample statement
        </a>
      </div>
      <p className="mt-3 max-w-2xl text-xs text-muted">
        Works with the CSV export from most Indian banks (not PDF). Only spending is imported (deposits are skipped),
        and uploading the same statement twice never creates duplicates.{" "}
        {demo ? (
          <strong>This is the shared demo account, so upload only the sample file here. Create your own account to use a real statement.</strong>
        ) : (
          <>
            Only the date, shop name, amount and category of each payment are stored; the file itself is not kept.
            You can delete everything any time from Account. See the{" "}
            <Link href="/privacy" className="text-accent hover:underline">
              privacy notice
            </Link>
            .
          </>
        )}
      </p>

      {error && <p className="mt-3 text-sm text-danger">{error}</p>}

      {result && (
        <div className="mt-4 rounded-xl border border-line p-4 text-sm">
          <p className="font-medium">
            Imported {result.imported} transaction{result.imported === 1 ? "" : "s"}
            {result.date_from && ` from ${result.date_from} to ${result.date_to}`}
          </p>
          <ul className="mt-2 space-y-0.5 text-muted">
            {result.duplicates_skipped > 0 && <li>{result.duplicates_skipped} already in your account (skipped)</li>}
            {result.credits_ignored > 0 && <li>{result.credits_ignored} deposits ignored (not spending)</li>}
            {result.uncategorized > 0 && (
              <li>{result.uncategorized} left as Uncategorized (the model wasn&apos;t sure, so it didn&apos;t guess)</li>
            )}
            {result.unusual > 0 && <li className="text-danger">{result.unusual} flagged as unusually large</li>}
            {result.invalid_rows > 0 && <li>{result.invalid_rows} rows couldn&apos;t be read</li>}
          </ul>
          {result.assumed_all_expenses && (
            <p className="mt-2 text-xs text-muted">
              Note: this file has no debit/credit marker, so every amount was treated as spending.
            </p>
          )}
          {result.problems.length > 0 && (
            <details className="mt-2 text-xs text-muted">
              <summary className="cursor-pointer">See unreadable rows</summary>
              <ul className="mt-1 list-disc pl-5">
                {result.problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </details>
          )}
          {result.preview.length > 0 && (
            <table className="mt-3 w-full text-xs">
              <tbody>
                {result.preview.map((r, i) => (
                  <tr key={i} className="border-t border-line/60">
                    <td className="py-1.5 pr-3 text-muted">{r.date}</td>
                    <td className="py-1.5 pr-3 font-medium">{r.merchant}</td>
                    <td className="py-1.5 pr-3">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full" style={{ background: categoryColor(r.category) }} />
                        {r.category}
                      </span>
                    </td>
                    <td className={`py-1.5 text-right tabular-nums ${r.is_anomaly ? "font-semibold text-danger" : ""}`}>
                      {formatINRExact(r.amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

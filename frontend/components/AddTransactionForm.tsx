"use client";

import { FormEvent, useState } from "react";
import { api, ApiError, CATEGORY_COLORS, Transaction } from "@/lib/api";

interface Props {
  onCreated: (txn: Transaction) => void;
}

// Add a transaction by hand. Leave the category on "Auto" and the ML model picks it.
export default function AddTransactionForm({ onCreated }: Props) {
  const [merchant, setMerchant] = useState("");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const txn = await api<Transaction>("/transactions", {
        method: "POST",
        body: {
          merchant: merchant.trim(),
          amount: Number(amount),
          category: category || null,
        },
      });
      onCreated(txn);
      setMerchant("");
      setAmount("");
      setCategory("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the transaction");
    } finally {
      setBusy(false);
    }
  }

  const input =
    "w-full rounded-lg border border-line bg-page px-3 py-2 text-sm outline-none focus:border-accent";

  return (
    <form onSubmit={submit} className="grid gap-3 p-5 sm:grid-cols-[1fr_140px_190px_auto] sm:items-end">
      <label className="text-xs text-muted">
        Merchant
        <input
          className={`${input} mt-1`}
          placeholder="e.g. Swiggy"
          value={merchant}
          onChange={(e) => setMerchant(e.target.value)}
          required
        />
      </label>
      <label className="text-xs text-muted">
        Amount (₹)
        <input
          className={`${input} mt-1`}
          type="number"
          min="0.01"
          step="0.01"
          placeholder="420"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          required
        />
      </label>
      <label className="text-xs text-muted">
        Category
        <select className={`${input} mt-1`} value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">Auto (ML picks)</option>
          {Object.keys(CATEGORY_COLORS)
            .filter((c) => c !== "Uncategorized")
            .map((c) => (
              <option key={c}>{c}</option>
            ))}
        </select>
      </label>
      <button
        disabled={busy}
        className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-60"
      >
        {busy ? "Adding…" : "Add"}
      </button>
      {error && <p className="text-sm text-danger sm:col-span-4">{error}</p>}
    </form>
  );
}

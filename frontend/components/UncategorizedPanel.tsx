"use client";

import { CATEGORY_CHOICES, formatINR, UncategorizedMerchant } from "@/lib/api";

interface Props {
  items: UncategorizedMerchant[];
  onChoose: (merchant: string, category: string) => void;
}

// Shops the app couldn't categorise on its own. Pick a category once and it is applied to
// every transaction from that shop, now and in future imports.
export default function UncategorizedPanel({ items, onChoose }: Props) {
  if (items.length === 0) return null;

  const rows = items.reduce((sum, m) => sum + m.count, 0);

  return (
    <section className="mt-4 rounded-2xl border border-line bg-surface">
      <div className="border-b border-line px-5 py-3">
        <h2 className="text-sm font-medium">Needs a category</h2>
        <p className="mt-0.5 text-xs text-muted">
          {rows} transaction{rows === 1 ? "" : "s"} from {items.length} shop{items.length === 1 ? "" : "s"} the app
          wasn&apos;t sure about. Choose a category once and it&apos;s remembered for every past and future
          transaction from that shop.
        </p>
      </div>
      <ul className="max-h-96 divide-y divide-line/60 overflow-y-auto">
        {items.map((m) => (
          <li key={m.merchant.toLowerCase()} className="flex flex-wrap items-center justify-between gap-3 px-5 py-2.5 text-sm">
            <span className="min-w-0">
              <span className="font-medium">{m.merchant}</span>
              <span className="ml-2 text-xs text-muted">
                {m.count} × · {formatINR(m.total)}
              </span>
            </span>
            <select
              aria-label={`Category for ${m.merchant}`}
              value=""
              onChange={(e) => e.target.value && onChoose(m.merchant, e.target.value)}
              className="rounded-lg border border-line bg-page px-2 py-1.5 text-sm outline-none focus:border-accent"
            >
              <option value="">Choose category…</option>
              {CATEGORY_CHOICES.filter((c) => c !== "Uncategorized").map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </li>
        ))}
      </ul>
    </section>
  );
}

import { CATEGORY_CHOICES, categoryColor, formatINRExact, Transaction } from "@/lib/api";

interface Props {
  transactions: Transaction[];
  fresh: Set<number>; // ids that just arrived live, to highlight briefly
  // when given, the category becomes a dropdown; the choice applies to the whole merchant
  onRecategorize?: (merchant: string, category: string) => void;
}

const when = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });

export default function TransactionsTable({ transactions, fresh, onRecategorize }: Props) {
  if (transactions.length === 0) {
    return <p className="p-6 text-sm text-muted">No transactions yet. Add one or start the simulator.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
            <th className="px-5 py-3 font-medium">When</th>
            <th className="px-5 py-3 font-medium">Merchant</th>
            <th className="px-5 py-3 font-medium">Category</th>
            <th className="px-5 py-3 text-right font-medium">Amount</th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((t) => (
            <tr
              key={t.id}
              className={`border-b border-line/60 last:border-0 ${fresh.has(t.id) ? "flash" : ""}`}
            >
              <td className="whitespace-nowrap px-5 py-3 text-muted">{when(t.occurred_at)}</td>
              <td className="px-5 py-3 font-medium">
                {t.merchant}
                {t.is_anomaly && (
                  <span className="ml-2 rounded-full bg-danger/15 px-2 py-0.5 text-xs font-medium text-danger">
                    unusual
                  </span>
                )}
              </td>
              <td className="px-5 py-3">
                <span className="inline-flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full" style={{ background: categoryColor(t.category) }} />
                  {onRecategorize ? (
                    <select
                      aria-label={`Category for ${t.merchant}`}
                      title="Change the category for every transaction from this shop"
                      value={t.category}
                      onChange={(e) => onRecategorize(t.merchant, e.target.value)}
                      className="cursor-pointer rounded border border-transparent bg-transparent py-0.5 pr-1 hover:border-line focus:border-accent"
                    >
                      {CATEGORY_CHOICES.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  ) : (
                    t.category
                  )}
                </span>
              </td>
              <td
                className={`whitespace-nowrap px-5 py-3 text-right tabular-nums ${
                  t.is_anomaly ? "font-semibold text-danger" : ""
                }`}
              >
                {formatINRExact(t.amount)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

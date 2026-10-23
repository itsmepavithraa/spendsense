import { formatINR, Subscription } from "@/lib/api";

// Recurring charges the backend detected (same merchant, same amount, about every month).
export default function SubscriptionsCard({ items }: { items: Subscription[] }) {
  const monthly = items.reduce((sum, s) => sum + s.amount, 0);
  const yearly = items.reduce((sum, s) => sum + s.yearly_cost, 0);

  return (
    <div className="rounded-2xl border border-line bg-surface p-5">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-medium">Subscriptions detected</h2>
        <span className="text-xs text-muted">{items.length} found</span>
      </div>

      {items.length === 0 ? (
        <p className="mt-4 text-sm text-muted">No recurring charges found yet.</p>
      ) : (
        <>
          <p className="mt-2 text-2xl font-semibold tabular-nums">
            {formatINR(monthly)}
            <span className="text-sm font-normal text-muted"> / month</span>
          </p>
          <p className="text-xs text-muted">{formatINR(yearly)} a year</p>
          <ul className="mt-3 divide-y divide-line text-sm">
            {items.map((s) => (
              <li key={`${s.merchant}-${s.amount}`} className="flex items-center justify-between py-2">
                <span>
                  {s.merchant}
                  <span className="ml-2 text-xs text-muted">{s.charges} charges</span>
                </span>
                <span className="tabular-nums text-muted">{formatINR(s.amount)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

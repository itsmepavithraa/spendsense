export interface ToastItem {
  id: number;
  message: string;
}

// Anomaly alerts that slide in at the top-right and dismiss themselves.
export default function Toasts({ items, onDismiss }: { items: ToastItem[]; onDismiss: (id: number) => void }) {
  return (
    <div className="pointer-events-none fixed right-4 top-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2">
      {items.map((t) => (
        <div
          key={t.id}
          role="alert"
          className="slide-in pointer-events-auto flex items-start gap-3 rounded-xl border border-danger/40 bg-surface p-3 shadow-lg"
        >
          <span className="mt-0.5 text-danger">⚠</span>
          <div className="flex-1 text-sm">
            <p className="font-medium text-danger">Unusual spending</p>
            <p className="text-muted">{t.message}</p>
          </div>
          <button onClick={() => onDismiss(t.id)} aria-label="Dismiss" className="text-muted hover:text-ink">
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

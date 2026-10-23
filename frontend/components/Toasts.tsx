export interface ToastItem {
  id: number;
  message: string;
  // anomaly = unusual-spending alert, error = something failed, info = success / neutral
  kind: "anomaly" | "error" | "info";
}

const STYLE = {
  anomaly: { title: "Unusual spending", icon: "⚠", color: "text-danger", border: "border-danger/40" },
  error: { title: "Something went wrong", icon: "✕", color: "text-danger", border: "border-danger/40" },
  info: { title: "Done", icon: "✓", color: "text-good", border: "border-good/40" },
} as const;

// Notifications that slide in at the top-right and dismiss themselves.
export default function Toasts({ items, onDismiss }: { items: ToastItem[]; onDismiss: (id: number) => void }) {
  return (
    <div className="pointer-events-none fixed right-4 top-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2">
      {items.map((t) => {
        const s = STYLE[t.kind];
        return (
          <div
            key={t.id}
            role={t.kind === "info" ? "status" : "alert"}
            className={`slide-in pointer-events-auto flex items-start gap-3 rounded-xl border bg-surface p-3 shadow-lg ${s.border}`}
          >
            <span className={`mt-0.5 ${s.color}`}>{s.icon}</span>
            <div className="flex-1 text-sm">
              <p className={`font-medium ${s.color}`}>{s.title}</p>
              <p className="text-muted">{t.message}</p>
            </div>
            <button onClick={() => onDismiss(t.id)} aria-label="Dismiss" className="text-muted hover:text-ink">
              ×
            </button>
          </div>
        );
      })}
    </div>
  );
}

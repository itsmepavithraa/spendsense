interface Props {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "danger";
}

export default function StatCard({ label, value, hint, tone = "default" }: Props) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-5">
      <p className="text-sm text-muted">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${tone === "danger" ? "text-danger" : ""}`}>
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

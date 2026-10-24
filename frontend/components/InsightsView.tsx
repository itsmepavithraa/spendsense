"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { categoryColor, formatINR, formatINRExact, InsightTip, Insights } from "@/lib/api";

const TIP_STYLE: Record<InsightTip["priority"], { label: string; badge: string }> = {
  high: { label: "Biggest saving", badge: "bg-danger/15 text-danger" },
  medium: { label: "Worth a look", badge: "bg-amber-500/15 text-amber-600" },
  low: { label: "Good to know", badge: "bg-line text-muted" },
  good: { label: "Good news", badge: "bg-good/15 text-good" },
};

const shortDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
const trim = (s: string, n = 20) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="print-keep rounded-2xl border border-line bg-surface p-5">
      <h2 className="text-sm font-medium">{title}</h2>
      {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function HorizontalBars({ rows }: { rows: { name: string; total: number; color: string }[] }) {
  return (
    <div style={{ height: Math.max(180, rows.length * 34) }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ left: 4, right: 64, top: 0, bottom: 0 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="name" width={120} tickLine={false} axisLine={false} fontSize={12} />
          <Tooltip formatter={(v) => formatINR(Number(v))} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
          <Bar dataKey="total" radius={[0, 4, 4, 0]} isAnimationActive={false}>
            {rows.map((r) => (
              <Cell key={r.name} fill={r.color} />
            ))}
            <LabelList dataKey="total" position="right" fontSize={11} formatter={(v: unknown) => formatINR(Number(v))} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function InsightsView({ data }: { data: Insights }) {
  const { totals, period } = data;

  if (totals.payments === 0) {
    return (
      <p className="rounded-2xl border border-line bg-surface p-8 text-center text-sm text-muted">
        {data.summary_lines[0]}
      </p>
    );
  }

  const potential = data.suggestions.reduce((sum, t) => sum + (t.monthly_saving ?? 0), 0);
  const change = totals.change_pct;

  return (
    <div className="space-y-4">
      {/* at a glance */}
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          { label: "Spent", value: formatINR(totals.spent), hint: `${period.from} to ${period.to}` },
          { label: "Per day", value: formatINR(totals.daily_average), hint: `over ${period.days} days` },
          { label: "Payments", value: String(totals.payments), hint: `${data.small_spends.count} under ${formatINR(data.small_spends.threshold)}` },
          {
            label: "Compared with before",
            value: change === null ? "Not enough history" : `${change > 0 ? "+" : ""}${change.toFixed(0)}%`,
            hint: change === null ? "needs a full earlier period" : `before: ${formatINR(totals.previous_spent ?? 0)}`,
            tone: change === null ? "" : change > 0 ? "text-danger" : "text-good",
          },
        ].map((k) => (
          <div key={k.label} className="print-keep rounded-2xl border border-line bg-surface p-5">
            <p className="text-sm text-muted">{k.label}</p>
            <p className={`mt-1 text-xl font-semibold tabular-nums ${"tone" in k ? k.tone : ""}`}>{k.value}</p>
            <p className="mt-1 text-xs text-muted">{k.hint}</p>
          </div>
        ))}
      </section>

      {/* the story in plain words */}
      <Card title="In plain words">
        <ul className="space-y-1.5 text-sm">
          {data.summary_lines.map((line) => (
            <li key={line} className="flex gap-2">
              <span className="text-accent">•</span>
              <span>{line}</span>
            </li>
          ))}
        </ul>
      </Card>

      {/* how to save: the main point */}
      <Card
        title="How to save"
        subtitle="Worked out from your own payments. The amounts are estimates, not promises, and this is not financial advice."
      >
        {data.suggestions.length === 0 ? (
          <p className="text-sm text-muted">Nothing stands out in this period. Your spending looks steady.</p>
        ) : (
          <>
            {potential > 0 && (
              <p className="mb-3 rounded-xl bg-accent/10 px-4 py-3 text-sm">
                Acting on these could free up about <strong>{formatINR(potential)} a month</strong>
                <span className="text-muted"> (some tips overlap, so treat it as an upper estimate).</span>
              </p>
            )}
            <ol className="space-y-3">
              {data.suggestions.map((t, i) => (
                <li key={t.id} className="print-keep rounded-xl border border-line p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-medium">
                      {i + 1}. {t.title}
                    </p>
                    <span className="flex items-center gap-2 text-xs">
                      {t.monthly_saving ? (
                        <span className="rounded-full bg-good/15 px-2.5 py-1 font-semibold text-good">
                          Save about {formatINR(t.monthly_saving)}/month
                        </span>
                      ) : null}
                      <span className={`rounded-full px-2.5 py-1 font-medium ${TIP_STYLE[t.priority].badge}`}>
                        {TIP_STYLE[t.priority].label}
                      </span>
                    </span>
                  </div>
                  <p className="mt-1.5 text-sm text-muted">{t.detail}</p>
                </li>
              ))}
            </ol>
          </>
        )}
      </Card>

      {/* where the money goes */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Where your money went" subtitle="By category, biggest first">
          <HorizontalBars
            rows={data.by_category.map((c) => ({ name: `${c.category} · ${c.share_pct}%`, total: c.total, color: categoryColor(c.category) }))}
          />
        </Card>
        <Card title="Top shops" subtitle="Where you paid the most in total">
          <HorizontalBars rows={data.top_merchants.map((m) => ({ name: `${trim(m.merchant)} · ${m.count}×`, total: m.total, color: "#6366f1" }))} />
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Day by day" subtitle="Spikes show the days that cost the most">
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.daily} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="dayFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#6366f1" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#94a3b8" strokeOpacity={0.25} vertical={false} />
                <XAxis dataKey="date" tickFormatter={shortDate} tickLine={false} axisLine={false} fontSize={11} minTickGap={24} />
                <YAxis tickLine={false} axisLine={false} fontSize={11} width={44} tickFormatter={(v) => `${Math.round(Number(v))}`} />
                <Tooltip labelFormatter={(l) => shortDate(String(l))} formatter={(v) => formatINR(Number(v))} />
                <Area type="monotone" dataKey="total" stroke="#6366f1" strokeWidth={2} fill="url(#dayFill)" isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Which weekday" subtitle="Total spent on each day of the week">
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.by_weekday} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#94a3b8" strokeOpacity={0.25} vertical={false} />
                <XAxis dataKey="weekday" tickLine={false} axisLine={false} fontSize={12} />
                <YAxis tickLine={false} axisLine={false} fontSize={11} width={44} />
                <Tooltip formatter={(v) => formatINR(Number(v))} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
                <Bar dataKey="total" fill="#6366f1" radius={[4, 4, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* small payments and biggest payments */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card
          title="Small payments add up"
          subtitle={`${data.small_spends.count} payments under ${formatINR(data.small_spends.threshold)} came to ${formatINR(data.small_spends.total)}`}
        >
          {data.small_spends.top_merchants.length === 0 ? (
            <p className="text-sm text-muted">No small payments in this period.</p>
          ) : (
            <ul className="divide-y divide-line text-sm">
              {data.small_spends.top_merchants.map((m) => (
                <li key={m.merchant} className="flex items-center justify-between py-2">
                  <span>
                    {m.merchant} <span className="text-xs text-muted">{m.count} payments</span>
                  </span>
                  <span className="tabular-nums text-muted">{formatINR(m.total)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Biggest payments" subtitle="Check that each one was planned">
          <ul className="divide-y divide-line text-sm">
            {data.largest.map((p, i) => (
              <li key={`${p.date}-${i}`} className="flex items-center justify-between py-2">
                <span>
                  {p.merchant} <span className="text-xs text-muted">{p.date} · {p.category}</span>
                </span>
                <span className="tabular-nums font-medium">{formatINRExact(p.amount)}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}

/** The same report as plain text, for download or pasting into a message. */
export function insightsToText(data: Insights): string {
  const lines: string[] = ["SPENDSENSE: SPENDING REPORT", `Period: ${data.period.from} to ${data.period.to} (${data.period.days} days)`, ""];
  lines.push("IN PLAIN WORDS", ...data.summary_lines.map((l) => `- ${l}`), "");
  lines.push("WHERE THE MONEY WENT");
  data.by_category.forEach((c) => lines.push(`- ${c.category}: ${formatINR(c.total)} (${c.share_pct}%) over ${c.count} payments`));
  lines.push("", "TOP SHOPS");
  data.top_merchants.forEach((m) => lines.push(`- ${m.merchant}: ${formatINR(m.total)} over ${m.count} payments`));
  lines.push("", "HOW TO SAVE");
  if (data.suggestions.length === 0) lines.push("- Nothing stands out in this period.");
  data.suggestions.forEach((t, i) => {
    lines.push(`${i + 1}. ${t.title}${t.monthly_saving ? ` (save about ${formatINR(t.monthly_saving)} a month)` : ""}`, `   ${t.detail}`);
  });
  lines.push("", "Note: tips are rule-based estimates from your own transactions, not financial advice.");
  return lines.join("\n");
}

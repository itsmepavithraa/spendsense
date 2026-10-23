"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { categoryColor, formatINR, Summary } from "@/lib/api";

// Donut of total spend per category, with a legend that lists the amounts.
export default function CategoryDonut({ data }: { data: Summary["by_category"] }) {
  const total = data.reduce((sum, d) => sum + d.total, 0);

  return (
    <div className="rounded-2xl border border-line bg-surface p-5">
      <h2 className="text-sm font-medium">Spend by category</h2>
      <div className="mt-2 flex flex-col items-center gap-4 sm:flex-row">
        <div className="h-48 w-48 shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                dataKey="total"
                nameKey="category"
                innerRadius={52}
                outerRadius={84}
                paddingAngle={2}
                stroke="none"
              >
                {data.map((d) => (
                  <Cell key={d.category} fill={categoryColor(d.category)} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => formatINR(Number(value))} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <ul className="w-full space-y-1.5 text-sm">
          {data.map((d) => (
            <li key={d.category} className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-2">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ background: categoryColor(d.category) }}
                />
                {d.category}
              </span>
              <span className="tabular-nums text-muted">
                {formatINR(d.total)} · {total ? Math.round((d.total / total) * 100) : 0}%
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

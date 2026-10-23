"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatINR, Summary } from "@/lib/api";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const label = (ym: string) => MONTHS[Number(ym.split("-")[1]) - 1] ?? ym;

// Area chart of total spend per month for the last 12 months.
export default function MonthlyTrend({ data }: { data: Summary["monthly"] }) {
  const rows = data.map((d) => ({ ...d, name: label(d.month) }));

  return (
    <div className="rounded-2xl border border-line bg-surface p-5">
      <h2 className="text-sm font-medium">Monthly spend</h2>
      <div className="mt-3 h-52">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={rows} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="spendFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#6366f1" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#94a3b8" strokeOpacity={0.25} vertical={false} />
            <XAxis dataKey="name" tickLine={false} axisLine={false} fontSize={12} />
            <YAxis
              tickLine={false}
              axisLine={false}
              fontSize={12}
              width={48}
              tickFormatter={(v) => `${Math.round(Number(v) / 1000)}k`}
            />
            <Tooltip formatter={(value) => formatINR(Number(value))} />
            <Area type="monotone" dataKey="total" stroke="#6366f1" strokeWidth={2} fill="url(#spendFill)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

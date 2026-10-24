"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import AddTransactionForm from "@/components/AddTransactionForm";
import ImportStatement from "@/components/ImportStatement";
import CategoryDonut from "@/components/CategoryDonut";
import MonthlyTrend from "@/components/MonthlyTrend";
import StatCard from "@/components/StatCard";
import SubscriptionsCard from "@/components/SubscriptionsCard";
import Toasts, { ToastItem } from "@/components/Toasts";
import TransactionsTable from "@/components/TransactionsTable";
import UncategorizedPanel from "@/components/UncategorizedPanel";
import {
  api,
  ApiError,
  clearToken,
  downloadCsv,
  formatINR,
  getToken,
  LiveEvent,
  Subscription,
  Summary,
  Transaction,
  UncategorizedMerchant,
  User,
} from "@/lib/api";
import { startProCheckout } from "@/lib/razorpay";
import { useLiveFeed } from "@/lib/useLiveFeed";

const MAX_ROWS = 50;

export default function Dashboard() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [uncategorized, setUncategorized] = useState<UncategorizedMerchant[]>([]);
  const [fresh, setFresh] = useState<Set<number>>(new Set()); // rows that just arrived live
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [simulating, setSimulating] = useState(false);
  const [error, setError] = useState("");

  const toastId = useRef(0);
  const summaryTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const logout = useCallback(() => {
    clearToken();
    router.replace("/login");
  }, [router]);

  // ----- initial load -----
  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    Promise.all([
      api<User>("/auth/me"),
      api<Summary>("/analytics/summary"),
      api<Transaction[]>("/transactions?limit=25"),
      api<Subscription[]>("/analytics/subscriptions"),
      api<UncategorizedMerchant[]>("/merchants/uncategorized"),
    ])
      .then(([u, s, t, subs, unc]) => {
        setUser(u);
        setSummary(s);
        setTransactions(t);
        setSubscriptions(subs);
        setUncategorized(unc);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) logout(); // token expired
        else setError("Could not load your data. Is the API running on port 8000?");
      });
  }, [router, logout]);

  // ----- helpers for live updates -----
  // Re-fetch the totals/charts shortly after the last live event. Waiting a moment
  // means a burst of events causes one refresh instead of many.
  const scheduleSummaryRefresh = useCallback(() => {
    clearTimeout(summaryTimer.current);
    summaryTimer.current = setTimeout(() => {
      api<Summary>("/analytics/summary").then(setSummary).catch(() => {});
    }, 800);
  }, []);

  const addRow = useCallback(
    (txn: Transaction) => {
      setTransactions((prev) => (prev.some((p) => p.id === txn.id) ? prev : [txn, ...prev].slice(0, MAX_ROWS)));
      setFresh((prev) => new Set(prev).add(txn.id));
      setTimeout(() => {
        setFresh((prev) => {
          const next = new Set(prev);
          next.delete(txn.id);
          return next;
        });
      }, 2500);
      scheduleSummaryRefresh();
    },
    [scheduleSummaryRefresh],
  );

  const pushToast = useCallback((message: string, kind: ToastItem["kind"] = "anomaly") => {
    const id = ++toastId.current;
    setToasts((prev) => [...prev, { id, message, kind }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 7000);
  }, []);

  // After a bulk import, reload everything the page shows from the server.
  const refreshAll = useCallback(() => {
    Promise.all([
      api<Summary>("/analytics/summary"),
      api<Transaction[]>("/transactions?limit=25"),
      api<Subscription[]>("/analytics/subscriptions"),
      api<UncategorizedMerchant[]>("/merchants/uncategorized"),
    ])
      .then(([s, t, subs, unc]) => {
        setSummary(s);
        setTransactions(t);
        setSubscriptions(subs);
        setUncategorized(unc);
      })
      .catch(() => {});
  }, []);

  // Teach the app: set a merchant's category once; the server fixes every existing row
  // and remembers it for future imports.
  const recategorize = useCallback(
    async (merchant: string, category: string) => {
      try {
        const result = await api<{ updated: number }>("/merchants/category", {
          method: "PUT",
          body: { merchant, category },
        });
        pushToast(
          `${result.updated} transaction${result.updated === 1 ? "" : "s"} from ${merchant} set to ${category}. Remembered for future imports.`,
          "info",
        );
        refreshAll();
      } catch {
        pushToast("Could not save that category.", "error");
      }
    },
    [pushToast, refreshAll],
  );

  // ----- WebSocket: this is where "real time" happens -----
  const live = useLiveFeed((event: LiveEvent) => {
    if (event.type === "transaction.created") addRow(event.data);
    if (event.type === "anomaly.alert") pushToast(event.data.message);
    if (event.type === "transactions.recategorized") refreshAll(); // a correction made in another tab
    if (event.type === "transactions.imported") {
      refreshAll(); // also fires for an upload made in another tab or device
      pushToast(`Imported ${event.data.count} transactions.`, "info");
    }
  });

  // ----- Pro plan -----
  async function upgrade() {
    if (!user) return;
    try {
      const paid = await startProCheckout(user);
      if (paid) {
        setUser(await api<User>("/auth/me")); // is_pro is now true
        pushToast("You're on the Pro plan. CSV export is unlocked.", "info");
      }
    } catch (err) {
      pushToast(
        err instanceof ApiError && err.status === 503
          ? "Payments aren't set up yet. Add your Razorpay test keys to .env."
          : err instanceof Error
            ? err.message
            : "Payment failed",
        "error",
      );
    }
  }

  async function exportCsv() {
    if (!user?.is_pro) {
      pushToast("CSV export is a Pro feature. Upgrade to unlock it.", "info");
      return upgrade();
    }
    try {
      await downloadCsv();
    } catch {
      pushToast("Could not download the CSV", "error");
    }
  }

  async function toggleSimulator() {
    try {
      if (simulating) {
        await api("/simulate/stop", { method: "POST" });
      } else {
        await api("/simulate/start?interval=2", { method: "POST" });
      }
      setSimulating(!simulating);
    } catch {
      setError("Could not toggle the simulator");
    }
  }

  // stop timers when leaving the page
  useEffect(() => () => clearTimeout(summaryTimer.current), []);

  if (error) {
    return <p className="p-8 text-center text-danger">{error}</p>;
  }
  if (!user || !summary) {
    return <p className="p-8 text-center text-muted">Loading your dashboard…</p>;
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <Toasts items={toasts} onDismiss={(id) => setToasts((prev) => prev.filter((t) => t.id !== id))} />

      {/* header */}
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">
            Spend<span className="text-accent">Sense</span>
          </h1>
          <p className="text-sm text-muted">Welcome back, {user.full_name}</p>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`inline-flex items-center gap-2 rounded-full border border-line px-3 py-1 text-xs ${
              live ? "text-good" : "text-muted"
            }`}
          >
            <span className={`h-2 w-2 rounded-full ${live ? "animate-pulse bg-good" : "bg-muted"}`} />
            {live ? "Live" : "Reconnecting…"}
          </span>
          <Link
            href="/insights"
            className="rounded-lg border border-accent px-3 py-1.5 text-sm font-medium text-accent transition hover:bg-accent/10"
          >
            Insights &amp; savings
          </Link>
          {user.is_pro ? (
            <span className="rounded-full bg-accent/15 px-3 py-1 text-xs font-semibold text-accent">PRO</span>
          ) : (
            <button
              onClick={upgrade}
              className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white transition hover:opacity-90"
            >
              Upgrade to Pro · ₹199
            </button>
          )}
          <button
            onClick={toggleSimulator}
            className={`rounded-lg border px-3 py-1.5 text-sm transition ${
              simulating ? "border-danger text-danger" : "border-line hover:border-accent"
            }`}
          >
            {simulating ? "Stop bank feed" : "Simulate bank feed"}
          </button>
          <button onClick={logout} className="text-sm text-muted hover:text-ink">
            Log out
          </button>
        </div>
      </header>

      {/* headline numbers */}
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Total spend" value={formatINR(summary.total_spend)} hint="last 12 months" />
        <StatCard label="This month" value={formatINR(summary.this_month_spend)} />
        <StatCard label="Transactions" value={summary.transaction_count.toLocaleString("en-IN")} />
        <StatCard
          label="Unusual charges"
          value={String(summary.anomaly_count)}
          hint="flagged by the ML model"
          tone={summary.anomaly_count > 0 ? "danger" : "default"}
        />
      </section>

      {/* charts */}
      <section className="mt-4 grid gap-4 lg:grid-cols-2">
        <CategoryDonut data={summary.by_category} />
        <MonthlyTrend data={summary.monthly} />
      </section>

      {/* detected subscriptions */}
      <section className="mt-4">
        <SubscriptionsCard items={subscriptions} />
      </section>

      {/* shops the app couldn't categorise: fix once, remembered forever */}
      <UncategorizedPanel items={uncategorized} onChoose={recategorize} />

      {/* add + live feed */}
      <section className="mt-4 rounded-2xl border border-line bg-surface">
        <div className="border-b border-line px-5 py-3">
          <h2 className="text-sm font-medium">Add a transaction</h2>
        </div>
        <AddTransactionForm onCreated={addRow} />
      </section>

      <section className="mt-4 rounded-2xl border border-line bg-surface">
        <div className="border-b border-line px-5 py-3">
          <h2 className="text-sm font-medium">Import a bank statement</h2>
        </div>
        <ImportStatement onImported={refreshAll} />
      </section>

      <section className="mt-4 overflow-hidden rounded-2xl border border-line bg-surface">
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 className="text-sm font-medium">Recent transactions</h2>
          <button onClick={exportCsv} className="text-sm text-accent hover:underline">
            Export CSV {!user.is_pro && <span className="text-xs text-muted">(Pro)</span>}
          </button>
        </div>
        <TransactionsTable transactions={transactions} fresh={fresh} onRecategorize={recategorize} />
      </section>
    </div>
  );
}

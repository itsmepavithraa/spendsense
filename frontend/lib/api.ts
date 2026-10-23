// Small typed client for the SpendSense API.
// The JWT is kept in localStorage and attached to every request.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const WS_URL = API_URL.replace(/^http/, "ws"); // http -> ws, https -> wss

const TOKEN_KEY = "spendsense_token";

export const getToken = (): string | null =>
  typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY);
export const setToken = (token: string) => window.localStorage.setItem(TOKEN_KEY, token);
export const clearToken = () => window.localStorage.removeItem(TOKEN_KEY);

// ---------- types (mirror the FastAPI schemas) ----------
export interface User {
  id: number;
  email: string;
  full_name: string;
  is_pro: boolean;
}

export interface Transaction {
  id: number;
  amount: string; // the API sends money as a string like "250.50" to avoid float errors
  merchant: string;
  category: string;
  is_anomaly: boolean;
  occurred_at: string;
}

export interface Summary {
  total_spend: number;
  this_month_spend: number;
  transaction_count: number;
  anomaly_count: number;
  by_category: { category: string; total: number }[];
  monthly: { month: string; total: number }[];
}

export interface Subscription {
  merchant: string;
  amount: number;
  charges: number;
  avg_gap_days: number;
  last_charge: string;
  yearly_cost: number;
}

// events pushed by the server over the WebSocket
export type LiveEvent =
  | { type: "connected"; data: { user_id: number } }
  | { type: "transaction.created"; data: Transaction }
  | { type: "anomaly.alert"; data: Transaction & { message: string } };

// ---------- fetch wrapper ----------
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown; // sent as JSON
  form?: Record<string, string>; // sent as application/x-www-form-urlencoded (login)
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;

  if (options.form) {
    body = new URLSearchParams(options.form);
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const json = await res.json();
      detail = typeof json.detail === "string" ? json.detail : JSON.stringify(json.detail);
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** Download the user's transactions as a CSV file (Pro plan). */
export async function downloadCsv(): Promise<void> {
  const res = await fetch(`${API_URL}/transactions/export`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) {
    throw new ApiError(res.status, res.status === 402 ? "CSV export is a Pro feature" : res.statusText);
  }
  // turn the response into a file and click a temporary link to save it
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = "spendsense-transactions.csv";
  link.click();
  URL.revokeObjectURL(url);
}

// ---------- formatting helpers ----------
const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});
const inrExact = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
});

export const formatINR = (value: number | string) => inr.format(Number(value));
export const formatINRExact = (value: number | string) => inrExact.format(Number(value));

export const CATEGORY_COLORS: Record<string, string> = {
  "Food & Dining": "#f97316",
  Groceries: "#22c55e",
  Transport: "#0ea5e9",
  Shopping: "#a855f7",
  Entertainment: "#ec4899",
  Utilities: "#eab308",
  Health: "#14b8a6",
  Education: "#6366f1",
  Subscriptions: "#ef4444",
  Uncategorized: "#94a3b8",
};
export const categoryColor = (name: string) => CATEGORY_COLORS[name] ?? "#94a3b8";

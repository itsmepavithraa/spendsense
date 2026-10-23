// Opens Razorpay Checkout for the Pro plan.
//
//   1. ask OUR server for an order (the server decides the price)
//   2. show Razorpay's payment popup for that order
//   3. send the popup's result back to OUR server, which verifies the signature
//
// The popup is Razorpay's own page, so card details never touch our code.

import { api } from "./api";

interface Order {
  order_id: string;
  key_id: string;
  amount: number;
  currency: string;
}

interface CheckoutResult {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

interface RazorpayInstance {
  open: () => void;
}

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => RazorpayInstance;
  }
}

function loadCheckoutScript(): Promise<boolean> {
  return new Promise((resolve) => {
    if (window.Razorpay) return resolve(true);
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}

/** Resolves true once the payment is paid AND verified by our server, false if the popup was closed. */
export async function startProCheckout(user: { full_name: string; email: string }): Promise<boolean> {
  if (!(await loadCheckoutScript())) throw new Error("Could not load Razorpay Checkout. Check your connection.");

  const order = await api<Order>("/billing/create-order", { method: "POST" });

  return new Promise<boolean>((resolve, reject) => {
    const checkout = new window.Razorpay!({
      key: order.key_id,
      amount: order.amount,
      currency: order.currency,
      order_id: order.order_id,
      name: "SpendSense",
      description: "Pro plan",
      prefill: { name: user.full_name, email: user.email },
      theme: { color: "#4f46e5" },
      handler: async (result: CheckoutResult) => {
        try {
          await api("/billing/verify", { method: "POST", body: result });
          resolve(true);
        } catch (err) {
          reject(err);
        }
      },
      modal: { ondismiss: () => resolve(false) },
    });
    checkout.open();
  });
}

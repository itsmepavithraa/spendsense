import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SpendSense",
  description: "Real-time expense tracking with ML categorization and anomaly alerts",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

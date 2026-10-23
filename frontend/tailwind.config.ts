import type { Config } from "tailwindcss";

// Colors point at CSS variables (see app/globals.css) so light and dark mode
// switch automatically with the user's system setting.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        page: "var(--page)",
        surface: "var(--surface)",
        ink: "var(--ink)",
        muted: "var(--muted)",
        line: "var(--line)",
        accent: "var(--accent)",
        danger: "var(--danger)",
        good: "var(--good)",
      },
    },
  },
  plugins: [],
};

export default config;

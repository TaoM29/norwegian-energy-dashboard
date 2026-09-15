import type { Metadata } from "next";
import "./globals.css";
import "@/components/theme.css";
import { DataModeBanner } from "@/components/data-mode-banner";
import { ThemeProvider } from "@/components/theme-provider";

export const metadata: Metadata = {
  title: "Norwegian Energy Dashboard",
  description:
    "Explore Norwegian energy, weather, regional patterns and analytical diagnostics.",
};

const themeScript = `
(() => {
  const systemTheme = () => matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
  let mode = "system";
  try {
    const key = "energy-dashboard-theme";
    const stored = localStorage.getItem(key);
    mode = stored === "light" || stored === "dark" || stored === "system"
      ? stored
      : "system";
  } catch {}
  const resolved = mode === "system" ? systemTheme() : mode;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themeMode = mode;
  document.documentElement.style.colorScheme = resolved;
})();
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <ThemeProvider>
          <DataModeBanner />
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}

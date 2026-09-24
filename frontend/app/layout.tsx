import type { Metadata } from "next";
import "./globals.css";
import "@/components/theme.css";
import { DataModeBanner } from "@/components/data-mode-banner";
import { ThemeProvider } from "@/components/theme-provider";

export const metadata: Metadata = {
  title: "Norway Energy Atlas",
  description:
    "Explore energy production, demand and weather across Norway.",
};

const themeScript = `
(() => {
  let theme = "dark";
  try {
    const stored = localStorage.getItem("energy-dashboard-theme");
    theme = stored === "light" ? "light" : "dark";
  } catch {}
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
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

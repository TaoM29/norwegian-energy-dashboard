import type { Metadata } from "next";
import "./globals.css";
import { DataModeBanner } from "@/components/data-mode-banner";
export const metadata: Metadata = {
  title: "Norwegian Energy Dashboard",
  description:
    "Explore Norwegian energy, weather, regional patterns and analytical diagnostics.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <DataModeBanner />
        {children}
      </body>
    </html>
  );
}

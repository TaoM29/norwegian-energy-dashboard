import type { Metadata } from "next";
import "./globals.css";
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
      <body>{children}</body>
    </html>
  );
}

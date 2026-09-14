import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Norwegian Energy · Overview",
  description:
    "Explore observed Norwegian energy production and consumption, sourced from Elhub.",
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

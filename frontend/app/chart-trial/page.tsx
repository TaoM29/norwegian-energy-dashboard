"use client";

import dynamic from "next/dynamic";

const ChartTrial = dynamic(() => import("./trial"), {
  ssr: false,
  loading: () => <p className="trial-loading">Loading chart trial…</p>,
});

export default function ChartTrialPage() {
  return <ChartTrial />;
}

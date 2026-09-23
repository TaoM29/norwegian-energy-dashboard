"use client";
import { useEffect, useState } from "react";
export function DataModeBanner() {
  const [fixture, setFixture] = useState(false);
  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then((v) => setFixture(v.dataMode === "fixture"))
      .catch(() => {});
  }, []);
  return fixture ? (
    <div role="note" className="fixture-banner">
      Synthetic fixture data · demonstration only
    </div>
  ) : null;
}

"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Waves } from "lucide-react";
import "./analysis.css";

const navigation = [
  ["/", "Overview"],
  ["/explore", "Explore"],
  ["/forecasts", "Forecasts"],
  ["/diagnostics", "Diagnostics"],
  ["/regional", "Regional & snow"],
];

export function AnalysisShell({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  const [path, setPath] = useState("");
  const [query, setQuery] = useState("");
  useEffect(() => {
    const update = () => {
      setPath(window.location.pathname);
      const current = new URLSearchParams(window.location.search);
      const shared = new URLSearchParams();
      for (const key of ["area", "start", "end"])
        if (current.has(key)) shared.set(key, current.get(key)!);
      setQuery(shared.toString() ? `?${shared}` : "");
    };
    update();
    window.addEventListener("popstate", update);
    // Forms update their own URL without leaving the page. Read the latest
    // shared fields at navigation time too, rather than retaining old filters.
    return () => window.removeEventListener("popstate", update);
  }, []);
  function destination(href: string) {
    const current = new URLSearchParams(window.location.search);
    const shared = new URLSearchParams();
    for (const key of ["area", "start", "end"])
      if (current.has(key)) shared.set(key, current.get(key)!);
    return href + (shared.size ? `?${shared}` : "");
  }
  return (
    <div className="analysis-workspace">
      <a href="#analysis-main" className="skip-link">
        Skip to analysis
      </a>
      <header className="analysis-topbar">
        <a className="analysis-brand" href="/">
          <Waves size={26} />
          <span>norwegian energy</span>
        </a>
        <nav aria-label="Main navigation">
          {navigation.map(([href, label]) => (
            <a
              key={href}
              href={href + query}
              aria-current={path === href ? "page" : undefined}
              onClick={(event) => {
                event.currentTarget.href = destination(href);
              }}
            >
              {label}
            </a>
          ))}
        </nav>
      </header>
      <main className="analysis-main" id="analysis-main" tabIndex={-1}>
        <header className="analysis-heading">
          <span className="eyebrow">OBSERVATIONS & ANALYSIS</span>
          <h1>{title}</h1>
          <p>{description}</p>
        </header>
        {children}
        <footer className="analysis-footer">
          Elhub energy · Open-Meteo ERA5-Seamless weather · UTC intervals.
          Weather area views use a fixed city proxy. Statistical flags are
          candidates, not verified faults.
        </footer>
      </main>
    </div>
  );
}

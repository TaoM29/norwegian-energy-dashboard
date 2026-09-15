"use client";

import { type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { AppNavigation } from "./app-navigation";
import "./analysis.css";

export function AnalysisShell({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  const path = usePathname();
  const guides: Record<string, string> = {
    "/explore":
      "Start with daily energy totals to compare electricity sources or types of use. Switch to weather to explore temperature, rain and wind. A gap means missing observations, not zero. Open the values and provenance below each chart for the full detail.",
    "/forecasts":
      "A forecast is an estimate, not a promise. Compare the model line with what actually happened. Shaded bands show estimated uncertainty; the accuracy table shows how often those bands contained the outcome. Lower average error is better, but only when models are compared on the same observations.",
    "/diagnostics":
      "Look for relationships, recurring rhythms or unusual observations. Weather & energy compares how two series move together; seasonal patterns separates repeating cycles from longer trends. A relationship does not prove cause, and an unusual point is not automatically an error. The default settings are a starting point; method settings let you dig deeper.",
    "/regional":
      "The map compares Norway’s five electricity price areas. Snow transport is a separate model: choose a location to estimate how wind moves snow. It is a modeled estimate, not a measurement of snow at that point. Coverage and assumptions are shown with each result.",
  };
  return (
    <div className="analysis-workspace">
      <a href="#analysis-main" className="skip-link">
        Skip to analysis
      </a>
      <AppNavigation />
      <main className="analysis-main" id="analysis-main" tabIndex={-1}>
        <header className="analysis-heading">
          <span className="eyebrow">NORWAY, THROUGH THE DATA</span>
          <h1>{title}</h1>
          <p>{description}</p>
        </header>
        {guides[path] && (
          <details className="reading-guide">
            <summary>How to read this page</summary>
            <div>
              <p>{guides[path]}</p>
            </div>
          </details>
        )}
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

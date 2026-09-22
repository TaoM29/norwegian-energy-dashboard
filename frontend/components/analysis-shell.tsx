"use client";

import { type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { HelpPanel } from "./help";
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
      "Start with energy totals, weather or household demand peaks. Daily profiles compares weekday/weekend and seasonal patterns by Oslo hour. Its bands show variation across observed days, not uncertainty in a mean. A gap means missing observations, not zero. Use Export to save values and open each view’s method details for context.",
    "/forecasts":
      "A forecast is an estimate, not a promise. Compare the model line with what actually happened. Shaded bands show estimated uncertainty; the accuracy table shows how often those bands contained the outcome. Lower average error is better, but only when models are compared on the same observations.",
    "/diagnostics":
      "Look for relationships, recurring rhythms or unusual observations. Weather & energy compares how two series move together; seasonal patterns separates repeating cycles from longer trends. A relationship does not prove cause, and an unusual point is not automatically an error. The default settings are a starting point; method settings let you dig deeper.",
    "/regional":
      "The map compares Norway’s five electricity price areas. Demand peaks compares household energy only at hours observed in all five areas. Snow model is a separate estimate of wind-driven transport at one location. Coverage and assumptions are shown with each result.",
  };
  return (
    <div className="analysis-workspace">
      <a href="#analysis-main" className="skip-link">
        Skip to analysis
      </a>
      <AppNavigation />
      <main className="analysis-main" id="analysis-main" tabIndex={-1}>
        <header className="analysis-heading">
          <div>
            <h1>{title}</h1>
            <p>{description}</p>
          </div>
          {guides[path] && (
            <HelpPanel label="About this view">
              <p>{guides[path]}</p>
              <a href="/methods">Methods, sources and recorded evidence →</a>
            </HelpPanel>
          )}
        </header>
        {children}
        <footer className="analysis-footer">
          <span>Elhub energy · Open-Meteo weather</span>
          <a href="/methods">Methods & data</a>
        </footer>
      </main>
    </div>
  );
}

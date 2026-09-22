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
  compact = false,
}: {
  title: string;
  description: string;
  children: ReactNode;
  compact?: boolean;
}) {
  const path = usePathname();
  const guides: Record<string, string> = {
    "/explore":
      "Start with daily energy totals, switch to weather, or inspect household demand peaks and consecutive hourly changes. A gap means missing observations, not zero. Energy is shown in kilowatt-hours (kWh); hourly peaks do not measure instantaneous power. Use Export below a chart to save its image or data, and open the method details for more context.",
    "/forecasts":
      "A forecast is an estimate, not a promise. Compare the model line with what actually happened. Shaded bands show estimated uncertainty; the accuracy table shows how often those bands contained the outcome. Lower average error is better, but only when models are compared on the same observations.",
    "/diagnostics":
      "Look for relationships, recurring rhythms or unusual observations. Weather & energy compares how two series move together; seasonal patterns separates repeating cycles from longer trends. A relationship does not prove cause, and an unusual point is not automatically an error. The default settings are a starting point; method settings let you dig deeper.",
    "/regional":
      "The map compares Norway’s five electricity price areas. Demand peaks compares household energy only at hours observed in all five areas. Snow model is a separate estimate of wind-driven transport at one location. Coverage and assumptions are shown with each result.",
  };
  return (
    <div
      className={`analysis-workspace${compact ? " analysis-workspace-compact" : ""}`}
    >
      <a href="#analysis-main" className="skip-link">
        Skip to analysis
      </a>
      <AppNavigation />
      <main className="analysis-main" id="analysis-main" tabIndex={-1}>
        <header className="analysis-heading">
          {!compact && (
            <span className="eyebrow">NORWAY, THROUGH THE DATA</span>
          )}
          <h1>{title}</h1>
          <p>{description}</p>
        </header>
        {guides[path] && (
          <div className="reading-guide">
            <HelpPanel label="How this works">
              <p>{guides[path]}</p>
              <h3>Reading the results</h3>
              <p>
                Use the applied filters to check which region and dates you are
                viewing. Gaps mean missing data, not zero. Open Export for the
                chart image and available underlying values.
              </p>
              <a href="/methods">Methods, sources and recorded evidence →</a>
            </HelpPanel>
          </div>
        )}
        {children}
        <footer className="analysis-footer">
          <HelpPanel label="Sources & interpretation">
            <h3>Energy and weather</h3>
            <p>
              Energy observations come from Elhub. Weather uses Open-Meteo
              ERA5-Seamless reanalysis, with a fixed city proxy for each price
              area. Analytical intervals use UTC.
            </p>
            <h3>What the results mean</h3>
            <p>
              Statistical flags identify candidates for investigation, not
              verified faults. Forecast uncertainty is conditional on the saved
              model and assumptions. Snow transport is a model estimate, not a
              site measurement.
            </p>
            <a href="/methods">Open methods and data coverage →</a>
          </HelpPanel>
        </footer>
      </main>
    </div>
  );
}

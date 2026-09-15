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
      "Start with daily energy totals to compare electricity sources or types of use. Switch to weather to explore temperature, rain and wind. A gap means missing observations, not zero. Energy is shown in kilowatt-hours (kWh); 1,000 kWh equals 1 MWh. Use Export below a chart to save its image or data, and open the values and source details for more context.",
    "/forecasts":
      "A forecast is an estimate, not a promise. Compare the model line with what actually happened. Shaded bands show estimated uncertainty; the accuracy table shows how often those bands contained the outcome. Lower average error is better, but only when models are compared on the same observations.",
    "/diagnostics":
      "Look for relationships, recurring rhythms or unusual observations. Weather & energy compares how two series move together; seasonal patterns separates repeating cycles from longer trends. A relationship does not prove cause, and an unusual point is not automatically an error. The default settings are a starting point; method settings let you dig deeper.",
    "/regional":
      "The map compares Norway’s five electricity price areas. Switch to Snow model for a separate task: choose a location to estimate how wind moves snow. It is a modeled estimate, not a measurement of snow at that point. Coverage and assumptions are shown with each result.",
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

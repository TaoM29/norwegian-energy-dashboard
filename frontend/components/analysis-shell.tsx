"use client";

import { type ReactNode } from "react";
import { AppNavigation } from "./app-navigation";
import "./analysis.css";
import { ThemeToggle } from "./theme-toggle";

export function AnalysisShell({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
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
          </div>
          <ThemeToggle />
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

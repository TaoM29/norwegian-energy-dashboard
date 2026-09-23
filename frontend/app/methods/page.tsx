"use client";

import { useEffect, useState } from "react";
import { OverviewCaseStudies } from "@/components/overview-case-studies";
import { AnalysisShell } from "@/components/analysis-shell";
import styles from "./methods.module.css";
import { Coverage, getJson, shortDate } from "@/lib/api";

const models = [
  [
    "Seasonal naive",
    "Repeat the latest eligible observation at a 168-hour seasonal lag.",
    "A transparent weekly reference; changing weather and holidays can break repetition.",
  ],
  [
    "Ridge",
    "Regularized regression with calendar, eligible demand lags, rolling summaries and historical weather.",
    "Fold-local imputation and scaling; linear relationships can miss interactions.",
  ],
  [
    "Gradient boosting",
    "Trees using the same information available at issue time; validation selects the configuration.",
    "Nonlinear associations, not causal weather effects. Performance outside the training range is uncertain.",
  ],
  [
    "SARIMAX",
    "State-space forecasting with configurable orders and optional projected weather. The benchmark fixes ARMA(1,1).",
    "Convergence failures are reported. Custom nominal 95% intervals omit future-weather uncertainty.",
  ],
];

export default function Methods() {
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getJson<Coverage>("/api/coverage")
      .then(setCoverage)
      .catch(() =>
        setError(
          "The published snapshot is unavailable. Coverage cannot be confirmed.",
        ),
      );
  }, []);
  return (
    <AnalysisShell
      title="Methods & data"
    >
      <div className={styles.content}>
        <section id="recorded-evidence" className="analysis-panel">
          <h2>Evidence and coverage</h2>
          {coverage ? (
            <>
              <p>
                <strong>
                  {coverage.coverage.start} to {coverage.coverage.end}{" "}
                  (exclusive, UTC)
                </strong>{" "}
                · NO1–NO5
              </p>
              <p>
                Source: {coverage.snapshot.source}. Snapshot retrieved:{" "}
                {coverage.snapshot.retrievedAt ? `${shortDate(coverage.snapshot.retrievedAt)} ${coverage.snapshot.retrievedAt.slice(0, 4)} (UTC)` : "Unknown"}. Saved snapshot.
              </p>
            </>
          ) : (
            <p role="status">{error || "Checking the published snapshot…"}</p>
          )}
          <p className={styles.sourceLinks}>
            <a href="https://api.elhub.no/">Elhub energy</a> · <a href="https://open-meteo.com/en/docs/historical-weather-api">Open-Meteo weather</a> · <a href="https://github.com/TaoM29/norwegian-energy-dashboard/blob/main/docs/PHASE4_VALIDATION.md">Forecast validation</a> · <a href="https://github.com/TaoM29/norwegian-energy-dashboard">Source code</a>
          </p>
          <details className={styles.sourceDetails}>
            <summary>Sources & units</summary>
          <p>
            Energy is hourly kWh from <a href="https://api.elhub.no/">Elhub</a>.
            Overview totals use MWh and chart axes may use GWh. Production and
            consumption sum disjoint base groups. Their difference is not a
            measure of cross-border flows.
          </p>
          <p>
            Weather comes from{" "}
            <a href="https://open-meteo.com/en/docs/historical-weather-api">
              Open-Meteo historical weather
            </a>
            , using ERA5-Seamless. Area views use one fixed city proxy per area,
            not spatial averages. Snow drift uses the selected coordinate.
            Reanalysis and revised energy records do not reconstruct what was
            known historically.
          </p>
          </details>
        </section>
        <details className={styles.docDisclosure}>
          <summary>Forecast models and evaluation</summary>
        <section className={`analysis-panel ${styles.modelSection}`}>
          <h2>Forecast model cards</h2>
          <p>
            The flagship task predicts 24 hours of household demand in all five
            areas. Energy becomes eligible after the interval ends plus an
            assumed 48-hour publication lag; historical weather uses 120 hours.
            These are experimental assumptions, not verified publication
            archives.
          </p>
          <div className={styles.modelGrid}>
            {models.map(([name, method, limit]) => (
              <article className={styles.modelCard} key={name}>
                <h3>{name}</h3>
                <p>{method}</p>
                <p>{limit}</p>
              </article>
            ))}
          </div>
          <div className={styles.modelNotes}>
            <section>
              <h3>Evaluation protocol</h3>
              <p>
                Parameters are selected on chronological validation dates. Residual
                quantiles are calibrated before the final holdout. Later origins can
                refit using earlier observations once eligible, while selection and
                calibration remain frozen. Failed fits are recorded; comparison uses
                the same successful origins for every model.
              </p>
              <p>
                The broader reliability study evaluates 46 scheduled dates across
                2025, after validation in 2023 and interval calibration in 2024.
                These previously reviewed observations support exploratory
                comparisons, not untouched confirmation. Its uncertainty ranges
                resample blocks of forecast dates with all regions kept together;
                seasonal comparisons and results from few blocks remain tentative.
              </p>
            </section>
            <section>
              <h3>Reading the scores and intervals</h3>
              <p>
                MAE and RMSE measure held-out error. MASE uses training seasonal
                changes as its denominator; MASE below one does not prove a model
                beat the held-out baseline. Benchmark intervals use empirical
                10th/50th/90th residual quantiles. Evaluate coverage, width and
                pinball loss together. Realized future weather is available only as
                a separately labeled upper-bound experiment.
              </p>
            </section>
          </div>
        </section>
        </details>
        <details className={styles.docDisclosure}>
          <summary>Demand sensitivity</summary>
        <section className="analysis-panel">
          <h2>Weather-adjusted demand sensitivity</h2>
          <p>
            The <a href="/diagnostics?view=sensitivity">Demand sensitivity</a>
            study is a saved retrospective analysis of hourly household demand
            in NO1–NO5. It compares a calendar-only reference, a linear
            temperature response and a flexible temperature response on later
            observations. The page shows the study’s fixed training,
            validation and test dates; changing the dates in other dashboard
            views does not refit this study.
          </p>
          <p>
            The temperature curve is an adjusted association after accounting
            for hour, weekday, holidays and seasonality. Its shaded 95%
            pointwise band describes uncertainty in the estimated mean response,
            not the range for an individual hour. Temperature support and
            held-out error should be read alongside the curve, especially near
            the edges of the observed range.
          </p>
          <p>
            Each area uses one fixed city weather proxy rather than an
            area-wide temperature measure. The result is neither a causal
            temperature effect nor an operational weather forecast; demand
            scales differ across areas, so raw error values should not be used
            as a ranking without that context.
          </p>
        </section>
        </details>
        <details className={styles.docDisclosure}>
          <summary>Validation case studies</summary>
        <OverviewCaseStudies />
        </details>
        <details className={styles.docDisclosure}>
          <summary>Architecture and reproducibility</summary>
        <section className="analysis-panel">
          <h2>Architecture and reproducibility</h2>
          <p>
            Public sources → validated hourly SQLite and weather snapshots →
            FastAPI analysis and stored forecast artifacts → Next.js charts and
            tables. Refreshes publish atomically; ordinary area views read local
            snapshots. Only explicit custom jobs fit forecasting models, with
            one worker, a bounded queue, timeout and cancellation.
          </p>
          <p>
            UTC intervals use an exclusive end; browser date controls include
            both selected dates. Calendar features and daily profiles use
            Europe/Oslo. Profiles exclude partial, incomplete and 23/25-hour
            daylight-saving days from their 24-hour comparison, while retaining
            those days for inspection. Missing hours remain on the regular grid.
            Aggregation and display sampling are disclosed alongside each
            analysis.
          </p>
          <p>
            Exports carry source versions, parameters and units. Forecast
            artifacts also record training windows, issue times, code
            fingerprints, dependencies, failed folds and calibration.
            Reproducing an exact result requires the same source snapshots and
            environment.
          </p>
          <p>
            This independent continuation of{" "}
            <a href="https://github.com/TaoM29/data-to-descision-dashboard">
              the original IND320 project
            </a>{" "}
            preserves its notebooks, source attribution and historical
            validation in{" "}
            <a href="https://github.com/TaoM29/norwegian-energy-dashboard">
              the repository
            </a>
            . See its validation reports for full methods and recorded checks.
          </p>
        </section>
        </details>
        <details id="local-experiments" className={styles.docDisclosure}>
          <summary>Local experiments</summary>
          <section className="analysis-panel">
            <p>Custom forecast jobs are disabled on the public deployment. A local installation can run bounded evaluations and SARIMAX jobs with progress reporting and cancellation.</p>
            <p><a href="https://github.com/TaoM29/norwegian-energy-dashboard/blob/main/docs/RELEASE.md">Local setup and release instructions</a></p>
          </section>
        </details>
      </div>
    </AnalysisShell>
  );
}

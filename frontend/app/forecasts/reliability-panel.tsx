"use client";

import { useState } from "react";
import { formatDisplayValue } from "@/lib/number-format";
import styles from "./reliability-panel.module.css";

type RecordValue = Record<string, unknown>;

function object(value: unknown): RecordValue {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as RecordValue)
    : {};
}

function rows(value: unknown): RecordValue[] {
  return Array.isArray(value)
    ? value.filter((item): item is RecordValue =>
        !!item && typeof item === "object" && !Array.isArray(item),
      )
    : [];
}

function numeric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function count(value: unknown): string {
  const number = numeric(value);
  return number == null ? "Unavailable" : formatDisplayValue(number, 0);
}

function measure(value: unknown, digits = 1): string {
  const number = numeric(value);
  return number == null ? "—" : formatDisplayValue(number, digits);
}

function percent(value: unknown): string {
  const number = numeric(value);
  return number == null ? "—" : `${formatDisplayValue(number * 100, 1)}%`;
}

function delta(value: unknown): string {
  const number = numeric(value);
  return number == null ? "—" : `${number > 0 ? "+" : ""}${measure(number)}`;
}

function range(value: unknown): string {
  const interval = object(value);
  const lower = numeric(interval.lower);
  const upper = numeric(interval.upper);
  return lower == null || upper == null
    ? "Unavailable"
    : `${delta(lower)} to ${delta(upper)}`;
}

function modelName(value: unknown): string {
  const names: Record<string, string> = {
    seasonal_naive: "Seasonal baseline",
    ridge: "Ridge",
    gradient_boosting: "Gradient boosting",
    sarimax: "SARIMAX",
  };
  const key = typeof value === "string" ? value : "";
  return names[key] || key.replaceAll("_", " ") || "Unknown model";
}

const dependenceLabels: [string, string][] = [
  ["withinWindowLag1Hour", "Adjacent forecast hours"],
  ["exactTargetLag24Hours", "Target residuals, 24 h apart"],
  ["exactTargetLag168Hours", "Target residuals, 168 h apart"],
  ["originMeanLag8Days", "Origin means, 8 d apart"],
  ["originMeanLag16Days", "Origin means, 16 d apart"],
];

export function ReliabilityPanel({
  report,
  protocol,
  resultId,
  unit = "kWh",
}: {
  report: unknown;
  protocol: unknown;
  resultId: string;
  unit?: string;
}) {
  const [requestedArea, setRequestedArea] = useState("");
  const reliability = object(report);
  const models = rows(reliability.models);
  if (reliability.schemaVersion !== 1 || !models.length) return null;
  const support = object(reliability.support);
  const method = object(reliability.method);
  const study = object(protocol);
  const rowCounts = object(support.hourlyRowsPerModel);
  const missingDates = Array.isArray(support.missingDates)
    ? support.missingDates.filter((date): date is string => typeof date === "string")
    : [];
  const excluded = numeric(support.excludedAreaOrigins);
  const scheduled = numeric(support.scheduledAreaOrigins);
  const grouped = new Map<string, { origins: Set<string>; hours: number }>();
  const configuredAreas = object(study.config).areas;
  if (Array.isArray(configuredAreas)) {
    for (const area of configuredAreas) {
      if (typeof area === "string") grouped.set(area, { origins: new Set(), hours: 0 });
    }
  }
  // The report validates an identical matched cohort for every model.
  for (const origin of rows(models[0].byOrigin)) {
    if (typeof origin.area !== "string" || typeof origin.origin !== "string") continue;
    const current = grouped.get(origin.area) || { origins: new Set<string>(), hours: 0 };
    current.origins.add(origin.origin);
    current.hours += numeric(origin.observations) || 0;
    grouped.set(origin.area, current);
  }
  const areaSupport = [...grouped].map(([area, value]) => ({ area, ...value }));
  const residualAreas = [...new Set(models.flatMap((model) =>
    rows(object(model.residualDependence).byArea)
      .map((row) => row.area)
      .filter((area): area is string => typeof area === "string"),
  ))].sort();
  const selectedArea = residualAreas.includes(requestedArea) ? requestedArea : residualAreas[0];

  return (
    <section className={styles.panel} aria-labelledby="reliability-title">
      <div className={styles.heading}>
        <div>
          <h2 id="reliability-title">Reliability across dates</h2>
        </div>
        <span className={styles.protocol}>
          {typeof study.label === "string" ? study.label : "Saved Step 2 study"}
        </span>
      </div>
      <p className={styles.intro}>
        This exploratory study pools all five areas and matched dates. Chart
        filters do not change it. Negative paired MAE differences favor the
        model over the seasonal baseline; every difference uses matched targets.
      </p>
      <div className={styles.support} aria-label="Study support">
        <div>
          <span>Scheduled dates</span>
          <strong>{count(support.scheduledDates)}</strong>
        </div>
        <div>
          <span>Observed dates</span>
          <strong>{count(support.observedDates)}</strong>
        </div>
        <div>
          <span>Matched area-origins</span>
          <strong>{count(support.matchedAreaOrigins)}</strong>
        </div>
        <div>
          <span>Excluded area-origins</span>
          <strong>{count(support.excludedAreaOrigins)}</strong>
        </div>
      </div>
      <p className={styles.context}>
        {scheduled == null ? "Scheduled area-origins unavailable" : `${count(scheduled)} scheduled area-origins`}
        {excluded != null && excluded > 0
          ? "; exclusions and failures reduce the matched cohort."
          : "; all scheduled area-origins matched."}
        {missingDates.length
          ? ` Missing scheduled dates: ${missingDates.map((date) => date.slice(0, 10)).join(", ")}.`
          : " No scheduled date is missing."}
      </p>
      <div className={styles.tableWrap} role="region" aria-label="Reliability comparison" tabIndex={0}>
        <table>
          <caption>Paired differences and measured 80% predictive intervals · {unit} unless shown as %</caption>
          <thead>
            <tr>
              <th scope="col">Model</th>
              <th scope="col">Matched hours</th>
              <th scope="col">MAE − baseline</th>
              <th scope="col">Approx. 95% MAE range by date block</th>
              <th scope="col">Bias</th>
              <th scope="col">80% interval: measured coverage</th>
              <th scope="col">Mean width</th>
            </tr>
          </thead>
          <tbody>
            {models.map((model, index) => {
              const name = typeof model.model === "string" ? model.model : "";
              const overall = object(model.overall);
              const blocks = rows(object(model.uncertainty).byBlockLength);
              return (
                <tr key={`${name}-${index}`}>
                  <th scope="row">{modelName(name)}</th>
                  <td>{count(rowCounts[name])}</td>
                  <td>{name === "seasonal_naive" ? "Reference" : delta(overall.maeDeltaVsBaseline)}</td>
                  <td>
                    {name === "seasonal_naive" ? "Reference" : blocks.length ? (
                      <ul className={styles.ranges}>
                        {blocks.map((block, blockIndex) => (
                          <li key={blockIndex}>
                            {count(block.blockLengthDates)} dates: {range(object(block.intervals).maeDeltaVsBaseline)}
                            {typeof block.reason === "string" && block.reason ? ` (${block.reason})` : ""}
                          </li>
                        ))}
                      </ul>
                    ) : "Unavailable"}
                  </td>
                  <td>{measure(overall.bias)}</td>
                  <td>{percent(overall.intervalCoverage)}</td>
                  <td>{measure(overall.meanIntervalWidth)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className={styles.limitations}>
        The 80% target is nominal; coverage is measured on these saved outcomes.
        Bias is actual minus forecast, so a positive value means underprediction.
        The approximate ranges resample consecutive origin dates in blocks of
        2, 4 and 8, keeping areas together. Dependence and the limited number
        of dates can make these ranges unstable; a range crossing zero does not
        establish an improvement. This previously reviewed period is
        exploratory, not an untouched confirmation set.
      </p>
      <p className={styles.intro}>
        <a href={`/api/forecasts/results/${encodeURIComponent(resultId)}/artifact`}>
          Download complete study JSON
        </a>
        {" · "}Includes predictions, calibration residuals, uncertainty ranges and provenance.
      </p>
      <details className={styles.details}>
        <summary>Support and residual dependence</summary>
        <div className={styles.detailsBody}>
          <p>
            {typeof method.supportRule === "string" ? method.supportRule : "Rows are weighted equally across matched area-origins."}
          </p>
          {areaSupport.length > 0 && (
            <div className={styles.tableWrap} role="region" aria-label="Reliability support by area" tabIndex={0}>
              <table className={styles.supportTable}>
                <caption>Matched support by area, shared by every model</caption>
                <thead><tr><th scope="col">Area</th><th scope="col">Matched origins</th><th scope="col">Hourly rows</th></tr></thead>
                <tbody>{areaSupport.map((row, index) => <tr key={`${row.area}-${index}`}>
                  <th scope="row">{row.area}</th>
                  <td>{count(row.origins.size)}</td><td>{count(row.hours)}</td>
                </tr>)}</tbody>
              </table>
            </div>
          )}
          {selectedArea && <label className={styles.areaSelect}>
            Residual area
            <select value={selectedArea} onChange={(event) => setRequestedArea(event.target.value)}>
              {residualAreas.map((area) => <option key={area} value={area}>{area}</option>)}
            </select>
          </label>}
          <p>Sampling only some forecast dates can leave daily or weekly residual lags without enough pairs to estimate a correlation.</p>
          <div className={styles.tableWrap} role="region" aria-label="Residual dependence diagnostics" tabIndex={0}>
            <table>
              <caption>{selectedArea ? `${selectedArea} residual correlation diagnostics` : "Pooled-area residual correlation diagnostics"}; pair counts describe available comparisons</caption>
              <thead><tr><th scope="col">Model</th><th scope="col">Comparison</th><th scope="col">Pairs</th><th scope="col">Correlation</th></tr></thead>
              <tbody>
                {models.flatMap((model, index) => dependenceLabels.map(([key, label]) => {
                  const dependence = object(model.residualDependence);
                  const area = rows(dependence.byArea).find((row) => row.area === selectedArea);
                  const diagnostic = object(selectedArea ? area?.[key] : dependence[key]);
                  return <tr key={`${index}-${key}`}>
                    <th scope="row">{modelName(model.model)}</th>
                    <td>{label}</td><td>{count(diagnostic.pairs)}</td>
                    <td>{numeric(diagnostic.correlation) == null ? "—" : formatDisplayValue(diagnostic.correlation, 3)}{typeof diagnostic.reason === "string" && diagnostic.reason ? ` (${diagnostic.reason})` : ""}</td>
                  </tr>;
                }))}
              </tbody>
            </table>
          </div>
        </div>
      </details>
    </section>
  );
}

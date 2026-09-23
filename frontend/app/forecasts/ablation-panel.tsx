"use client";

import type { CSSProperties } from "react";
import { formatDisplayValue } from "@/lib/number-format";
import { modelColour } from "./forecast-chart";
import styles from "./ablation-panel.module.css";

type Row = Record<string, unknown>;

function object(value: unknown): Row {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Row : {};
}

function rows(value: unknown): Row[] {
  return Array.isArray(value) ? value.filter((item): item is Row =>
    !!item && typeof item === "object" && !Array.isArray(item)) : [];
}

function numeric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function count(value: unknown): string {
  const parsed = numeric(value);
  return parsed == null ? "Unavailable" : formatDisplayValue(parsed, 0);
}

function measure(value: unknown, digits = 1): string {
  const parsed = numeric(value);
  return parsed == null ? "Unavailable" : formatDisplayValue(parsed, digits);
}

function percent(value: unknown): string {
  const parsed = numeric(value);
  return parsed == null ? "Unavailable" : `${formatDisplayValue(parsed * 100, 1)}%`;
}

function signed(value: unknown, suffix = " kWh"): string {
  const parsed = numeric(value);
  return parsed == null ? "Unavailable" : `${parsed > 0 ? "+" : ""}${measure(parsed)}${suffix}`;
}

function interval(value: unknown, suffix = " kWh", scale = 1): string {
  const range = object(value);
  return numeric(range.lower) == null || numeric(range.upper) == null
    ? "Unavailable"
    : `${signed(numeric(range.lower)! * scale, suffix)} to ${signed(numeric(range.upper)! * scale, suffix)}`;
}

function variantLabel(variant: Row): string {
  return text(variant.label) || ({
    calendar: "Calendar only",
    calendar_demand: "Calendar + demand history",
    calendar_demand_weather: "Calendar + demand + eligible weather",
  }[text(variant.featureSet)] || text(variant.model).replaceAll("_", " "));
}

function featureColumns(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string");
  const features = object(value);
  if (Array.isArray(features.columns)) return featureColumns(features.columns);
  return Object.values(object(features.groupColumns)).flatMap(featureColumns);
}

const additionalMeasures = [
  ["Bias", "bias"],
  ["Lower pinball", "pinballLower"],
  ["Median pinball", "pinballMedian"],
  ["Upper pinball", "pinballUpper"],
] as const;
const uncertaintyMeasures = [
  ["MAE", "mae"], ["RMSE", "rmse"], ["Coverage", "intervalCoverage"],
  ["Width", "meanIntervalWidth"], ["Lower pinball", "pinballLower"],
  ["Median pinball", "pinballMedian"], ["Upper pinball", "pinballUpper"],
] as const;

export function AblationPanel({
  report, resultId, unit = "kWh",
}: { report: unknown; resultId: string; unit?: string }) {
  const ablation = object(report);
  const variants = rows(ablation.variants);
  if (ablation.schemaVersion !== 1 || !variants.length) return null;
  const contrasts = rows(ablation.contrasts);
  const support = object(ablation.support);
  const rowCounts = object(support.hourlyRowsPerModel);
  const maxMae = Math.max(0, ...variants.map((variant) => numeric(object(variant.overall).mae) ?? 0));
  const rawMissingDates = support.missingDates;
  const missingDatesKnown = Array.isArray(rawMissingDates);
  const missingDates: string[] = Array.isArray(rawMissingDates)
    ? rawMissingDates.filter((date: unknown): date is string => typeof date === "string") : [];
  const scheduled = numeric(support.scheduledAreaOrigins);
  const excluded = numeric(support.excludedAreaOrigins);

  return (
    <section className={styles.panel} aria-labelledby="ablation-title">
      <div className={styles.heading}>
        <div>
          <h2 id="ablation-title">What each input adds</h2>
        </div>
        <span className={styles.protocol}>Feature ablation · ridge</span>
      </div>
      <p className={styles.intro}>
        Three ridge variants use the same matched, previously inspected 2025 dates.
        The controls on the forecast chart do not change this saved comparison.
        Results are retrospective and exploratory; gradient boosting is outside this study.
      </p>
      <div className={styles.support} aria-label="Feature ablation support">
        <div><span>Scheduled dates</span><strong>{count(support.scheduledDates)}</strong></div>
        <div><span>Observed dates</span><strong>{count(support.observedDates)}</strong></div>
        <div><span>Matched area-origins</span><strong>{count(support.matchedAreaOrigins)}</strong></div>
        <div><span>Excluded area-origins</span><strong>{count(support.excludedAreaOrigins)}</strong></div>
      </div>
      <p className={styles.context}>
        {scheduled == null ? "Scheduled area-origins unavailable" : `${count(scheduled)} scheduled area-origins`}
        {excluded == null ? "; exclusion count unavailable."
          : excluded > 0 ? "; exclusions and failures reduce the common matched cohort."
          : "; all scheduled area-origins matched."}
        {!missingDatesKnown ? " Missing-date status unavailable."
          : missingDates.length
          ? ` Missing scheduled dates: ${missingDates.map((date) => date.slice(0, 10)).join(", ")}.`
          : " No scheduled date is missing."}
      </p>
      <div className={styles.tableWrap} role="region" aria-label="Feature ablation variant comparison" tabIndex={0}>
        <table>
          <caption>Absolute error and measured predictive interval quality · {unit} unless shown as %. MAE bars share a zero baseline.</caption>
          <thead><tr>
            <th scope="col">Ridge inputs</th><th scope="col">Matched hours</th>
            <th scope="col">MAE</th><th scope="col">RMSE</th>
            <th scope="col">80% interval: measured coverage</th><th scope="col">Mean width</th>
          </tr></thead>
          <tbody>{variants.map((variant, index) => {
            const overall = object(variant.overall);
            const model = text(variant.model);
            return <tr key={`${model}-${index}`}>
              <th scope="row">{variantLabel(variant)}</th>
              <td>{count(rowCounts[model])}</td>
              <td>
                {measure(overall.mae)}
                {numeric(overall.mae) != null && maxMae > 0 && (
                  <span className={styles.maeTrack} aria-hidden="true">
                    <span style={{ width: `${Math.max(0, Number(overall.mae)) / maxMae * 100}%`, background: modelColour(model).token } as CSSProperties} />
                  </span>
                )}
              </td><td>{measure(overall.rmse)}</td>
              <td>{percent(overall.intervalCoverage)}</td><td>{measure(overall.meanIntervalWidth)}</td>
            </tr>;
          })}</tbody>
        </table>
      </div>
      <div className={styles.tableWrap} role="region" aria-label="Feature ablation added-input contrasts" tabIndex={0}>
        <table>
          <caption>Added inputs minus the preceding variant · negative error change means lower error</caption>
          <thead><tr>
            <th scope="col">Added inputs</th><th scope="col">Δ MAE</th><th scope="col">Δ RMSE</th>
            <th scope="col">Δ coverage</th><th scope="col">Δ width</th>
            <th scope="col">Approx. 95% range for Δ MAE by date block</th>
          </tr></thead>
          <tbody>{contrasts.map((contrast, index) => {
            const overall = object(contrast.overall);
            const blocks = rows(object(contrast.uncertainty).byBlockLength);
            const label = text(contrast.label) || (contrast.id === "demand" ? "Add demand history" : "Add eligible weather");
            return <tr key={`${text(contrast.id)}-${index}`}>
              <th scope="row">{label}</th>
              <td>{signed(overall.mae, ` ${unit}`)}</td>
              <td>{signed(overall.rmse, ` ${unit}`)}</td>
              <td>{signed(numeric(overall.intervalCoverage) == null ? null : numeric(overall.intervalCoverage)! * 100, " pp")}</td>
              <td>{signed(overall.meanIntervalWidth, ` ${unit}`)}</td>
              <td><ul className={styles.ranges}>{[2, 4, 8].map((length) => {
                const block = blocks.find((item) => numeric(item.blockLengthDates) === length);
                const range = object(object(block?.intervals).mae);
                const reason = text(block?.reason);
                return <li key={length}>{length} dates: {interval(range, ` ${unit}`)}
                  {reason ? ` (${reason})` : ""}</li>;
              })}</ul></td>
            </tr>;
          })}</tbody>
        </table>
      </div>
      <p className={styles.limitations}>
        Coverage changes are percentage points. Higher coverage is not automatically better without considering width;
        a narrower interval alone is not an improvement. Approximate ranges resample consecutive origin dates
        in blocks of 2, 4 and 8, keeping areas together. Missing ranges remain unavailable. Predictive value
        does not establish a causal weather effect.
      </p>
      <details className={styles.details}>
        <summary>Bias, pinball scores, area results and exact features</summary>
        <div className={styles.detailsBody}>
          <p>Each ridge variant uses the same availability rules and alpha candidates (0.1, 1 and 10), selected independently per area on validation origins.</p>
          {variants.map((variant, index) => {
            const model = text(variant.model);
            const overall = object(variant.overall);
            const columns = featureColumns(variant.features);
            return <section key={`${model}-${index}`} aria-label={`${variantLabel(variant)} details`}>
              <h3>{variantLabel(variant)}</h3>
              <p>{additionalMeasures.map(([label, key]) => `${label}: ${measure(overall[key])} ${unit}`).join(" · ")}</p>
              <p>Exact predictors ({columns.length}): {columns.length ? columns.join(", ") : "Unavailable"}</p>
              <div className={styles.tableWrap} role="region" aria-label={`${variantLabel(variant)} area results`} tabIndex={0}>
                <table className={styles.areaTable}>
                  <caption>Saved area scores · {unit} unless shown as %</caption>
                  <thead><tr><th scope="col">Area</th><th scope="col">Matched hours</th><th scope="col">Origins</th><th scope="col">MAE</th><th scope="col">RMSE</th><th scope="col">Bias</th><th scope="col">Coverage</th><th scope="col">Width</th></tr></thead>
                  <tbody>{rows(variant.byArea).map((area, areaIndex) => <tr key={`${text(area.area)}-${areaIndex}`}>
                    <th scope="row">{text(area.area)}</th><td>{count(area.observations)}</td><td>{count(area.origins)}</td><td>{measure(area.mae)}</td><td>{measure(area.rmse)}</td>
                    <td>{measure(area.bias)}</td><td>{percent(area.intervalCoverage)}</td><td>{measure(area.meanIntervalWidth)}</td>
                  </tr>)}</tbody>
                </table>
              </div>
            </section>;
          })}
          <section aria-label="Added-input pinball changes">
            <h3>Added-input pinball changes</h3>
            {contrasts.map((contrast, index) => {
              const overall = object(contrast.overall);
              return <p key={`${text(contrast.id)}-${index}`}>
                {text(contrast.label)}: lower {signed(overall.pinballLower, ` ${unit}`)} · median {signed(overall.pinballMedian, ` ${unit}`)} · upper {signed(overall.pinballUpper, ` ${unit}`)}
              </p>;
            })}
          </section>
          <section aria-label="Full paired uncertainty ranges">
            <h3>Full paired uncertainty ranges</h3>
            <p>Approximate 95% ranges for added inputs minus the preceding variant. Coverage ranges use percentage points; all other scores use {unit}.</p>
            {contrasts.map((contrast, index) => {
              const blocks = rows(object(contrast.uncertainty).byBlockLength);
              const label = text(contrast.label) || text(contrast.id);
              return <div className={styles.tableWrap} role="region" aria-label={`${label} uncertainty ranges`} tabIndex={0} key={`${text(contrast.id)}-${index}`}>
                <table className={styles.uncertaintyTable}>
                  <caption>{label} · consecutive date blocks</caption>
                  <thead><tr><th scope="col">Block</th><th scope="col">Effective blocks</th><th scope="col">Valid resamples</th>
                    {uncertaintyMeasures.map(([name]) => <th scope="col" key={name}>{name}</th>)}
                  </tr></thead>
                  <tbody>{[2, 4, 8].map((length) => {
                    const block = blocks.find((item) => numeric(item.blockLengthDates) === length);
                    const intervals = object(block?.intervals);
                    return <tr key={length}>
                      <th scope="row">{length} dates</th>
                      <td>{count(block?.effectiveObservedBlocks)}</td><td>{count(block?.validResamples)}</td>
                      {uncertaintyMeasures.map(([name, key]) => <td key={name}>
                        {interval(intervals[key], key === "intervalCoverage" ? " pp" : ` ${unit}`, key === "intervalCoverage" ? 100 : 1)}
                        {text(block?.reason) && numeric(object(intervals[key]).lower) == null ? ` (${text(block?.reason)})` : ""}
                      </td>)}
                    </tr>;
                  })}</tbody>
                </table>
              </div>;
            })}
          </section>
          <p>Bias is actual minus forecast. Full predictions, failure records and uncertainty diagnostics are in the saved artifact.</p>
          <p>Annual-cycle variation and non-circular block endpoints can affect these ranges. The ranges condition on the selected models and frozen interval calibration; their estimation uncertainty is not included.</p>
        </div>
      </details>
      <p className={styles.download}>
        <a href={`/api/forecasts/results/${encodeURIComponent(resultId)}/artifact`}>Download complete study JSON</a>
      </p>
    </section>
  );
}

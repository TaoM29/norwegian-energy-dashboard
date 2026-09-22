"use client";

import { useMemo, type CSSProperties } from "react";
import type { EChartsCoreOption } from "echarts/core";
import AnalysisChart from "@/components/analysis-chart";
import { ExportMenu } from "@/components/export-menu";
import { downloadCsv, downloadJson } from "@/lib/download";
import { modelColour } from "./forecast-chart";
import styles from "./error-explorer.module.css";

type Row = Record<string, unknown>;
export type ErrorExplorerView = "area" | "season" | "peak_period" | "horizon";
export type ErrorExplorerMeasure = "error" | "coverage";

type Props = {
  metrics: Row[];
  predictions: Row[];
  failures: Row[];
  coverage: unknown;
  config: unknown;
  resultId: string;
  exploratory: boolean;
  view: ErrorExplorerView;
  onViewChange: (view: ErrorExplorerView) => void;
  measure: ErrorExplorerMeasure;
  onMeasureChange: (measure: ErrorExplorerMeasure) => void;
  onInspect: (selection: { area: string; model: string; origin: string }) => void;
};

const viewLabels: Record<ErrorExplorerView, string> = {
  area: "Price areas",
  season: "Seasons",
  peak_period: "Peak periods",
  horizon: "Forecast horizon",
};
const knownModels: Record<string, string> = {
  seasonal_naive: "Seasonal baseline",
  ridge: "Ridge",
  ridge_calendar: "Ridge · calendar",
  ridge_calendar_demand: "Ridge · calendar + demand",
  ridge_calendar_demand_weather: "Ridge · calendar + demand + weather",
  gradient_boosting: "Gradient boosting",
  sarimax: "SARIMAX",
};
const baselineKey = "seasonal_naive";

function object(value: unknown): Row {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Row : {};
}

function numeric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function count(value: unknown): string {
  const parsed = numeric(value);
  return parsed == null ? "Unavailable" : parsed.toLocaleString("en-GB");
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function modelKey(row: Row): string {
  const name = text(row.model || row.modelName || row.name);
  return name === "baseline" ? baselineKey : name;
}

function modelLabel(model: string): string {
  return knownModels[model] || model.replaceAll("_", " ") || "Unknown model";
}

function areaKey(row: Row): string { return text(row.area || row.priceArea); }
function originKey(row: Row): string { return text(row.origin || row.forecastOrigin || row.issueTime); }

function metricDelta(row: Row): number | null {
  const saved = numeric(row.maeDeltaVsBaseline);
  if (saved != null) return saved;
  const mae = numeric(row.mae);
  const baseline = numeric(row.baselineMae);
  return mae == null || baseline == null ? null : mae - baseline;
}

function formatted(value: number | null, unit = " kWh", signed = false): string {
  if (value == null) return "Unavailable";
  return `${signed && value > 0 ? "+" : ""}${value.toLocaleString("en-GB", { maximumFractionDigits: 1, minimumFractionDigits: 1 })}${unit}`;
}

function coverageText(value: number | null): string {
  return value == null ? "Unavailable" : `${(value * 100).toFixed(1)}%`;
}

function scopeLabel(row: Row, view: ErrorExplorerView): string {
  if (view === "area") return areaKey(row) || "Unspecified area";
  if (view === "season") return text(row.season) || "Unspecified season";
  if (view === "horizon") {
    const value = numeric(row.horizon);
    return value == null ? "Unspecified horizon" : `Hour ${value}`;
  }
  if (typeof row.isPeakPeriod === "boolean") return row.isPeakPeriod ? "Peak period" : "Other hours";
  return "Unspecified period";
}

function matchingPredictions(row: Row, predictions: Row[]): Row[] {
  const scope = text(row.scope);
  const key = modelKey(row);
  return predictions.filter((item) => {
    if (modelKey(item) !== key) return false;
    if (scope === "area") return areaKey(item) === areaKey(row);
    if (scope === "season") return item.season === row.season;
    if (scope === "horizon") return numeric(item.horizon) === numeric(row.horizon);
    if (scope === "peak_period") return item.isPeakPeriod === row.isPeakPeriod;
    return false;
  });
}

function support(row: Row, predictions: Row[]) {
  const saved = matchingPredictions(row, predictions);
  const areaOrigins = new Set(saved.filter((item) => areaKey(item) && originKey(item)).map((item) => `${areaKey(item)}\u0000${originKey(item)}`));
  const dates = new Set(saved.map((item) => originKey(item).slice(0, 10)).filter(Boolean));
  return {
    hours: numeric(row.observations) ?? (saved.length ? saved.length : null),
    areaOrigins: numeric(row.areaOrigins) ?? (areaOrigins.size ? areaOrigins.size : null),
    dates: numeric(row.distinctOriginDates) ?? (dates.size ? dates.size : null),
  };
}

function worstSavedOrigin(row: Row, predictions: Row[]): string | null {
  const grouped = new Map<string, { sum: number; count: number }>();
  for (const item of matchingPredictions(row, predictions)) {
    const origin = originKey(item);
    const actual = numeric(item.actual ?? item.observed);
    const prediction = numeric(item.prediction ?? item.forecast);
    const baseline = numeric(item.baseline ?? item.seasonalNaive);
    if (!origin || actual == null || prediction == null || baseline == null) continue;
    const current = grouped.get(origin) || { sum: 0, count: 0 };
    current.sum += Math.abs(actual - prediction) - Math.abs(actual - baseline);
    current.count += 1;
    grouped.set(origin, current);
  }
  return [...grouped].sort((a, b) => b[1].sum / b[1].count - a[1].sum / a[1].count || a[0].localeCompare(b[0]))[0]?.[0] ?? null;
}

function escapeHtml(value: unknown): string {
  return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char] || char);
}

function tooltip(params: unknown): string {
  const items = Array.isArray(params) ? params : [params];
  const first = object(items[0]);
  const hour = text(first.axisValue || first.name);
  const values = items.map((item) => {
    const point = object(item);
    const value = Array.isArray(point.value) ? point.value.at(-1) : point.value;
    const number = numeric(value);
    const unit = text(point.seriesName).includes("coverage") || text(point.seriesName).includes("Nominal") ? "%" : " kWh";
    return `${escapeHtml(point.seriesName)}: ${number == null ? "Unavailable" : escapeHtml(number.toFixed(1) + unit)}`;
  }).join("<br />");
  return `${hour ? `<strong>Hour ${escapeHtml(hour)} ahead</strong><br />` : ""}${values}`;
}

function horizonHours(rows: Row[], configuredHorizon: number | null): number[] {
  return configuredHorizon != null && Number.isInteger(configuredHorizon) && configuredHorizon > 0 && configuredHorizon <= 96
    ? Array.from({ length: configuredHorizon }, (_, index) => index + 1)
    : [...new Set(rows.map((row) => numeric(row.horizon)).filter((value): value is number => value != null))].sort((a, b) => a - b);
}

function horizonOption(rows: Row[], measure: ErrorExplorerMeasure, nominal: number | null, horizons: number[], models: string[]): EChartsCoreOption {
  const series: Row[] = [];
  for (const model of models) {
    const values = new Map(rows.filter((row) => modelKey(row) === model).map((row) => [numeric(row.horizon), row]));
    const data = horizons.map((horizon) => {
      const row = values.get(horizon);
      if (!row) return null;
      const value = measure === "error" ? numeric(row.mae) : numeric(row.intervalCoverage);
      return value == null ? null : measure === "coverage" ? value * 100 : value;
    });
    if (data.every((value) => value == null)) continue;
    series.push({
      name: `${modelLabel(model)} ${measure === "coverage" ? "observed coverage" : "MAE"}`,
      type: "line", data, connectNulls: false, symbol: "circle", symbolSize: 5,
      lineStyle: { width: model === baselineKey ? 2 : 2.5, type: model === baselineKey ? "dashed" : "solid" },
      itemStyle: { color: modelColour(model).line }, color: modelColour(model).line,
    });
  }
  if (measure === "coverage" && nominal != null) {
    series.push({ name: "Nominal reference", type: "line", data: horizons.map(() => nominal * 100),
      symbol: "none", silent: true, lineStyle: { color: "#9a816a", type: "dotted", width: 1.5 },
      itemStyle: { color: "#9a816a" }, color: "#9a816a" });
  }
  return {
    grid: { left: 58, right: 22, top: 42, bottom: 48, containLabel: true },
    legend: { type: "scroll", top: 0 },
    tooltip: { trigger: "axis", formatter: tooltip, confine: true, extraCssText: "max-width:min(320px,calc(100vw - 32px));white-space:normal;" },
    xAxis: { type: "category", name: "Hours ahead", nameLocation: "middle", nameGap: 30, data: horizons.map(String), boundaryGap: false },
    yAxis: { type: "value", name: measure === "coverage" ? "Coverage (%)" : "MAE (kWh)", min: 0, max: measure === "coverage" ? 100 : undefined },
    series,
  } as EChartsCoreOption;
}

export function ErrorExplorer({ metrics, predictions, failures, coverage, config, resultId, exploratory, view, onViewChange, measure, onMeasureChange, onInspect }: Props) {
  const saved = useMemo(() => metrics.filter((row) => ["area", "season", "peak_period", "horizon"].includes(text(row.scope))), [metrics]);
  const rows = useMemo(() => saved.filter((row) => row.scope === view), [saved, view]);
  const cohort = object(coverage);
  const setup = object(config);
  const nominal = numeric(setup.interval_coverage ?? setup.intervalCoverage);
  const configuredAreas = Array.isArray(setup.areas) ? setup.areas.filter((value): value is string => typeof value === "string" && !!value) : [];
  const configuredModels = Array.isArray(setup.models) ? setup.models.filter((value): value is string => typeof value === "string" && !!value) : [];
  const areas = [...new Set([...configuredAreas, ...saved.filter((row) => row.scope === "area").map(areaKey).filter(Boolean)])].sort();
  const models = [...new Set([...configuredModels, ...saved.filter((row) => row.scope === "area").map(modelKey).filter(Boolean)])].sort((a, b) => a === baselineKey ? -1 : b === baselineKey ? 1 : a.localeCompare(b));
  const configuredHorizon = numeric(setup.horizon_hours ?? setup.horizon);
  const hours = horizonHours(rows, configuredHorizon);
  const horizonModels = [...new Set([...configuredModels, ...rows.map(modelKey).filter(Boolean)])].sort((a, b) => a === baselineKey ? -1 : b === baselineKey ? 1 : a.localeCompare(b));
  const horizonGrid = view === "horizon" ? hours.flatMap((hour) => horizonModels.map((model) => ({
    hour, model, row: rows.find((item) => numeric(item.horizon) === hour && modelKey(item) === model),
  }))) : [];
  const maxDelta = Math.max(1, ...saved.filter((row) => row.scope === "area").map((row) => Math.abs(metricDelta(row) ?? 0)));
  const toExportRow = (row: Row) => {
    const counts = support(row, predictions);
    return {
      view, group: scopeLabel(row, view), model: modelKey(row), savedMetric: true,
      maeKwh: numeric(row.mae), baselineMaeKwh: numeric(row.baselineMae),
      maeMinusBaselineKwh: metricDelta(row), observedCoverage: numeric(row.intervalCoverage),
      nominalCoverage: nominal, hourlyTargets: counts.hours,
      areaOrigins: counts.areaOrigins, distinctOriginDates: counts.dates,
    };
  };
  const exported = view === "area"
    ? areas.flatMap((area) => models.map((model) => {
      const row = rows.find((item) => areaKey(item) === area && modelKey(item) === model);
      return row ? toExportRow(row) : {
        view, group: area, model, savedMetric: false,
        maeKwh: null, baselineMaeKwh: null, maeMinusBaselineKwh: null,
        observedCoverage: null, nominalCoverage: nominal, hourlyTargets: null,
        areaOrigins: null, distinctOriginDates: null,
      };
    }))
    : view === "horizon"
      ? horizonGrid.map(({ hour, model, row }) => row ? toExportRow(row) : {
        view, group: `Hour ${hour}`, model, savedMetric: false,
        maeKwh: null, baselineMaeKwh: null, maeMinusBaselineKwh: null,
        observedCoverage: null, nominalCoverage: nominal, hourlyTargets: null,
        areaOrigins: null, distinctOriginDates: null,
      })
    : rows.map(toExportRow);
  const filename = `forecast-error-${resultId.replace(/[^a-zA-Z0-9_-]/g, "-")}-${view}`;
  const holdoutFailures = failures.filter((row) => ["holdout", "matched_holdout"].includes(text(row.stage || row.split || row.cohort)));
  const excluded = Array.isArray(cohort.areas) ? cohort.areas.filter((item): item is Row => !!item && typeof item === "object" && !Array.isArray(item)) : [];
  const horizonChart = useMemo(() => horizonOption(rows, measure, nominal, hours, horizonModels), [rows, measure, nominal, hours, horizonModels]);

  if (!saved.length) return null;
  return <section className={styles.panel} aria-labelledby="error-explorer-title">
    <div className={styles.heading}>
      <div>
        <h2 id="error-explorer-title">Forecast error explorer</h2>
      </div>
      <ExportMenu label="Export explorer">
        <button type="button" disabled={!exported.length} onClick={() => downloadCsv(`${filename}.csv`, exported)}>Displayed view CSV</button>
        <button type="button" disabled={!exported.length} onClick={() => downloadJson(`${filename}.json`, { resultId, view, measure: view === "horizon" ? measure : undefined, cohort: coverage, rows: exported })}>Displayed view JSON</button>
      </ExportMenu>
    </div>
    <p className={styles.intro}>{exploratory ? "Exploratory" : "Saved"} matched metrics cover all areas, models and dates; chart filters do not change them. MAE differences are kWh per hourly target: negative favors the model over the seasonal baseline.</p>
    <div className={styles.cohort} aria-label="Evaluation cohort support">
      <div><span>Attempted area-origins</span><strong>{count(cohort.attemptedOrigins)}</strong></div>
      <div><span>Matched area-origins</span><strong>{count(cohort.matchedOrigins)}</strong></div>
      <div><span>Excluded area-origins</span><strong>{count(cohort.failedOrigins)}</strong></div>
    </div>
    {(excluded.some((item) => Array.isArray(item.excludedOrigins) && item.excludedOrigins.length) || holdoutFailures.length > 0) && <details className={styles.exclusions}>
      <summary>Excluded origins and recorded failures</summary>
      <div className={styles.exclusionBody}>
        {excluded.map((item) => {
          const dates = Array.isArray(item.excludedOrigins) ? item.excludedOrigins.filter((value): value is string => typeof value === "string") : [];
          return dates.length ? <p key={areaKey(item)}><strong>{areaKey(item)}:</strong> {dates.join(", ")}</p> : null;
        })}
        {holdoutFailures.map((item, index) => <p key={`${areaKey(item)}-${originKey(item)}-${index}`}><strong>{areaKey(item) || "Area unavailable"} · {modelLabel(modelKey(item))} · {originKey(item) || "origin unavailable"}:</strong> {text(item.reason) || "Reason unavailable"}</p>)}
      </div>
    </details>}
    <div className={styles.controls}>
      <label htmlFor="error-explorer-view">Error explorer view</label>
      <select id="error-explorer-view" value={view} onChange={(event) => onViewChange(event.target.value as ErrorExplorerView)}>
        {(Object.keys(viewLabels) as ErrorExplorerView[]).map((item) => <option key={item} value={item}>{viewLabels[item]}</option>)}
      </select>
    </div>
    {view === "area" ? <>
      <p className={styles.note}>Each cell is a saved area × model MAE difference. Inspection opens its largest saved per-origin MAE increase versus the baseline.</p>
      <div className={styles.tableWrap} role="region" aria-label="Forecast error matrix" tabIndex={0}>
        <table className={styles.heatmap}>
          <caption>MAE minus seasonal baseline by price area and model · kWh; unavailable means no saved metric</caption>
          <thead><tr><th scope="col">Price area</th>{models.map((model) => <th scope="col" key={model}>{modelLabel(model)}</th>)}</tr></thead>
          <tbody>{areas.map((area) => <tr key={area}><th scope="row">{area}</th>{models.map((model) => {
            const row = rows.find((item) => areaKey(item) === area && modelKey(item) === model);
            const value = row ? metricDelta(row) : null;
            const counts = row ? support(row, predictions) : null;
            const origin = row && model !== baselineKey ? worstSavedOrigin(row, predictions) : null;
            const intensity = value == null ? 0 : Math.round(7 + 26 * Math.min(1, Math.abs(value) / maxDelta));
            const cellStyle = value == null || model === baselineKey ? undefined : { backgroundColor: `color-mix(in srgb, ${value <= 0 ? "var(--chart-series-1)" : "#d4774d"} ${intensity}%, var(--surface))` } as CSSProperties;
            return <td key={model} style={cellStyle}>{row ? <div className={styles.cell}>
              {origin ? <button type="button" className={styles.inspect} onClick={() => onInspect({ area, model, origin })} aria-label={`Inspect ${area}, ${modelLabel(model)}, worst saved baseline-relative example at ${origin}`}><strong>{model === baselineKey ? "Reference" : formatted(value, "", true)}</strong><span>Inspect saved forecast ↗</span></button> : <strong>{model === baselineKey ? "Reference" : formatted(value, "", true)}</strong>}
              <small>{count(counts?.hours)} hours · {count(counts?.areaOrigins)} area-origins · {count(counts?.dates)} dates</small>
            </div> : <span className={styles.unavailable}>Unavailable</span>}</td>;
          })}</tr>)}</tbody>
        </table>
      </div>
    </> : <>
      {view === "horizon" && <>
        <div className={styles.controls}>
          <label htmlFor="error-explorer-measure">Horizon measure</label>
          <select id="error-explorer-measure" value={measure} onChange={(event) => onMeasureChange(event.target.value as ErrorExplorerMeasure)}>
            <option value="error">Error (MAE)</option><option value="coverage">Observed coverage</option>
          </select>
        </div>
        <p className={styles.note}>{measure === "coverage" ? `Lines show observed interval coverage. The dotted nominal ${coverageText(nominal)} reference is a target, not measured coverage.` : "Lines show saved MAE by hours ahead. The dashed seasonal baseline is the same matched target cohort."} Gaps indicate unavailable saved metrics.</p>
        {rows.length > 0 && <AnalysisChart option={horizonChart} imageOption={{ title: { left: 20, top: 12, text: `${measure === "coverage" ? "Observed coverage" : "MAE"} by forecast hour`, subtext: `Saved matched cohort · ${resultId}` }, legend: { type: "plain", left: 20, right: 20, top: 62, textStyle: { fontSize: 11 } }, grid: { left: 58, right: 22, top: 110, bottom: 48, containLabel: true } }} label={`${measure === "coverage" ? "Observed interval coverage" : "Forecast MAE"} by hours ahead for saved matched cohort ${resultId}`} height={360} />}
      </>}
      {(view === "season" || view === "peak_period") && <p className={styles.note}>These comparisons are descriptive and use the artifact’s saved Europe/Oslo target-time classifications. Smaller seasonal or peak-period groups may be sparse; support is shown for each saved row. No unsaved group combinations are inferred.</p>}
      <div className={styles.tableWrap} role="region" aria-label={`${viewLabels[view]} saved metric comparison`} tabIndex={0}>
        <table>
          <caption>{viewLabels[view]} · saved metrics and support; unavailable values are never zero</caption>
          <thead><tr><th scope="col">{view === "season" ? "Season" : view === "peak_period" ? "Period" : "Hours ahead"}</th><th scope="col">Model</th><th scope="col">MAE</th><th scope="col">Baseline MAE</th><th scope="col">MAE − baseline</th><th scope="col">Observed coverage</th><th scope="col">Hourly targets</th><th scope="col">Area-origins</th><th scope="col">Origin dates</th></tr></thead>
          <tbody>{(view === "horizon" ? horizonGrid : [...rows].sort((a, b) => scopeLabel(a, view).localeCompare(scopeLabel(b, view)) || modelKey(a).localeCompare(modelKey(b))).map((row) => ({ row, model: modelKey(row), hour: numeric(row.horizon) }))).map(({ row, model, hour }, index) => {
            if (!row) return <tr key={`hour-${hour}-${model}`}><th scope="row">Hour {hour}</th><td>{modelLabel(model)}</td><td colSpan={7} className={styles.unavailable}>Unavailable · no saved metric or support for this model and hour</td></tr>;
            const counts = support(row, predictions);
            return <tr key={`${scopeLabel(row, view)}-${modelKey(row)}-${index}`}><th scope="row">{scopeLabel(row, view)}</th><td>{modelLabel(modelKey(row))}</td><td>{formatted(numeric(row.mae))}</td><td>{formatted(numeric(row.baselineMae))}</td><td>{modelKey(row) === baselineKey ? "Reference" : formatted(metricDelta(row), " kWh", true)}</td><td>{coverageText(numeric(row.intervalCoverage))}</td><td>{count(counts.hours)}</td><td>{count(counts.areaOrigins)}</td><td>{count(counts.dates)}</td></tr>;
          })}</tbody>
        </table>
      </div>
    </>}
    {!rows.length && <p className={styles.empty}>No saved {viewLabels[view].toLowerCase()} metrics are available for this result.</p>}
  </section>;
}

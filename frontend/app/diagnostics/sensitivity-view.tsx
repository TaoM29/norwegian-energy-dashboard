"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { EChartsCoreOption } from "echarts/core";

import { StudyError } from "@/components/study-error";
import AnalysisChart from "@/components/analysis-chart";
import { ExportMenu } from "@/components/export-menu";
import { HelpPanel } from "@/components/help";
import { Select } from "@/components/ui/select";
import { ApiError, getJson, areas, number } from "@/lib/api";
import { downloadCsv } from "@/lib/download";
import "./sensitivity.css";

type Score = { mae: number; rmse: number; bias: number; count: number };
type Model = {
  model: "calendar" | "linear" | "spline";
  label: string;
  validation: Score;
  test: Score;
  parameters: Record<string, unknown>;
};
type Split = {
  start: string;
  end: string;
  expectedHours: number;
  observedHours: number;
};
type AreaResult =
  | { area: string; status: "unavailable"; reason: string }
  | {
      area: string;
      status: "ok";
      selectedModel: Model["model"];
      referenceTemperature: number;
      curve: {
        temperature: number;
        effect: number | null;
        lower: number | null;
        upper: number | null;
        lower336: number | null;
        upper336: number | null;
        supported: boolean;
        count: number;
      }[];
      support: {
        min: number;
        max: number;
        bins: { temperature: number; count: number }[];
        byMonth: { month: number; count: number; min: number | null; max: number | null }[];
      };
      models: Model[];
      splits: { train: Split; validation: Split; test: Split };
      residuals: {
        acf: { lagHours: number; correlation: number | null; pairs: number }[];
        byHour: { hour: number; mean: number | null; count: number }[];
        byMonth: { month: number; mean: number | null; count: number }[];
      };
      sensitivity: { maxCurveDifference: number; harmonics: number; notes: string };
      predictions?: Record<string, unknown>[];
      metadata: Record<string, unknown>;
    };
type Study = {
  schemaVersion: number;
  id: string;
  createdAt: string;
  dataMode: "observed" | "fixture";
  protocol: Record<string, unknown>;
  areas: AreaResult[];
  metadata: Record<string, unknown>;
};
type AvailableArea = Extract<AreaResult, { status: "ok" }>;

const green = "#176b59";
const gold = "#d18d2f";
const slate = "#526a60";

function modelName(model: Model["model"]) {
  return model === "calendar"
    ? "Calendar only"
    : model === "linear"
      ? "Linear temperature"
      : "Flexible temperature";
}

function metric(value: number | null | undefined, digits = 1) {
  return number(value, digits);
}

function date(value: string) {
  return value.slice(0, 10);
}

function splitLabel(split: Split) {
  return `${date(split.start)}–${date(split.end)} UTC`;
}

function curveOption(area: AvailableArea): EChartsCoreOption {
  const points = area.curve;
  return {
    tooltip: {
      trigger: "axis",
      formatter: (items: unknown) => {
        const first = Array.isArray(items) ? items[0] : null;
        const index = (first as { dataIndex?: number } | null)?.dataIndex ?? -1;
        const point = points[index];
        if (!point) return "";
        return `${metric(point.temperature)} °C<br/>Adjusted difference: ${metric(point.effect)} kWh<br/>95% pointwise band: ${metric(point.lower)} to ${metric(point.upper)} kWh<br/>Development hours near temperature: ${number(point.count, 0)}${point.supported ? "" : "<br/>Outside supported range"}`;
      },
    },
    grid: { left: 80, right: 24, top: 30, bottom: 58 },
    xAxis: { type: "value", name: "Temperature (°C)", nameLocation: "middle", nameGap: 34, min: points[0]?.temperature, max: points.at(-1)?.temperature },
    yAxis: { type: "value", name: "Difference (kWh)", nameLocation: "middle", nameGap: 58, scale: true },
    series: [
      {
        name: "95% lower",
        type: "line",
        stack: "band",
        stackStrategy: "all",
        data: points.map((point) => [point.temperature, point.supported ? point.lower : null]),
        showSymbol: false,
        lineStyle: { opacity: 0 },
        itemStyle: { opacity: 0 },
        silent: true,
      },
      {
        name: "95% pointwise uncertainty",
        type: "line",
        stack: "band",
        stackStrategy: "all",
        data: points.map((point) => [point.temperature, point.supported && point.lower != null && point.upper != null ? point.upper - point.lower : null]),
        showSymbol: false,
        lineStyle: { opacity: 0 },
        itemStyle: { opacity: 0 },
        areaStyle: { color: "rgba(23,107,89,.20)" },
        silent: true,
      },
      {
        name: "Adjusted temperature difference",
        type: "line",
        data: points.map((point) => [point.temperature, point.supported ? point.effect : null]),
        showSymbol: false,
        connectNulls: false,
        lineStyle: { width: 3, color: green },
        itemStyle: { color: green },
        markLine: { symbol: "none", silent: true, lineStyle: { color: slate, type: "dashed", opacity: .65 }, data: [{ yAxis: 0 }] },
      },
    ],
  } as EChartsCoreOption;
}

function supportOption(area: AvailableArea): EChartsCoreOption {
  return {
    tooltip: { trigger: "axis", valueFormatter: (value: number) => `${number(value, 0)} hours` },
    grid: { left: 68, right: 20, top: 22, bottom: 58 },
    xAxis: { type: "value", name: "Temperature (°C)", nameLocation: "middle", nameGap: 34 },
    yAxis: { type: "value", name: "Development hours", min: 0 },
    series: [{ type: "bar", name: "Development hours", barMaxWidth: 26, itemStyle: { color: gold }, data: area.support.bins.map((bin) => [bin.temperature, bin.count]) }],
  } as EChartsCoreOption;
}

function residualOption(area: AvailableArea, kind: "acf" | "hour"): EChartsCoreOption {
  const acf = kind === "acf";
  return {
    tooltip: { trigger: "axis" },
    grid: { left: 60, right: 18, top: 20, bottom: 50 },
    xAxis: { type: "category", name: acf ? "Lag (hours)" : "Hour (Europe/Oslo)", data: acf ? area.residuals.acf.map((row) => row.lagHours) : area.residuals.byHour.map((row) => row.hour), nameLocation: "middle", nameGap: 32, axisLabel: { hideOverlap: true } },
    yAxis: { type: "value", name: acf ? "Correlation" : "Mean error (kWh)", scale: true },
    series: [{ type: "bar", name: acf ? "Residual autocorrelation" : "Mean error", itemStyle: { color: acf ? slate : gold }, data: acf ? area.residuals.acf.map((row) => row.correlation) : area.residuals.byHour.map((row) => row.mean), markLine: { symbol: "none", silent: true, lineStyle: { color: slate, type: "dashed", opacity: .55 }, data: [{ yAxis: 0 }] } }],
  } as EChartsCoreOption;
}

export default function SensitivityView({ area, onAreaChange }: { area: string; onAreaChange: (area: string) => void }) {
  const [study, setStudy] = useState<Study | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [missing, setMissing] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setMissing(false);
    try {
      const data = await getJson<Study>("/api/diagnostics/sensitivity");
      if (!Array.isArray(data.areas) || data.schemaVersion !== 1) throw new Error("The saved sensitivity study could not be read.");
      setStudy(data);
    } catch (problem) {
      setStudy(null);
      setMissing(problem instanceof ApiError && problem.status === 404 && /no saved/i.test(problem.message));
      setError(problem instanceof Error ? problem.message : "No saved sensitivity study is available.");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const selected = study?.areas.find((item) => item.area === area);
  const data = selected?.status === "ok" ? selected : null;
  const selectedModel = data?.models.find((item) => item.model === data.selectedModel);
  const curve = useMemo(() => data ? curveOption(data) : null, [data]);
  const support = useMemo(() => data ? supportOption(data) : null, [data]);
  const acf = useMemo(() => data ? residualOption(data, "acf") : null, [data]);
  const byHour = useMemo(() => data ? residualOption(data, "hour") : null, [data]);
  const stem = `demand-sensitivity-${area.toLowerCase()}`;

  return <div className="sensitivity-view">
    <div className="sensitivity-intro">
      <div>

        <h2>Temperature & demand</h2>
        <p>Household demand adjusted for calendar patterns. A saved study with fixed dates.</p>
      </div>
      <label>Price area
        <Select aria-label="Sensitivity price area" value={area} onChange={(event) => onAreaChange(event.target.value)}>
          {Object.entries(areas).map(([code, name]) => <option key={code} value={code}>{code} · {name}</option>)}
        </Select>
      </label>
    </div>
    {loading && <div className="diagnostics-state" role="status">Loading saved demand sensitivity study…</div>}
    {error && <StudyError message={error} missing={missing} onRetry={() => void load()} />}
    {study && <>
      <div className="sensitivity-study-strip">
        <span>{study.dataMode === "fixture" ? "Fixture study" : "Observed-data study"}</span>
        <span>Saved {date(study.createdAt)}</span>

        <ExportMenu label="Export study">
          <a href="/api/diagnostics/sensitivity/artifact" download>Complete artifact JSON</a>
          {data && <button type="button" onClick={() => downloadCsv(`${stem}-curve.csv`, data.curve)}>Selected area curve CSV</button>}
        </ExportMenu>
      </div>
      {data ? <>
        <section className="analysis-panel sensitivity-primary">
          <div className="sensitivity-section-heading"><div><h2>Adjusted temperature response</h2><p>Difference from {metric(data.referenceTemperature)} °C under the same calendar conditions. An adjusted association, not a causal effect.</p></div></div>
          {data.selectedModel === "calendar" && <div className="sensitivity-callout">Temperature did not improve validation enough to select a temperature model. The calendar-only response is zero.</div>}
          {curve && <AnalysisChart option={curve} height={390} label={`${area} adjusted household-demand response to temperature with 95 percent pointwise uncertainty band`} exports={<button type="button" onClick={() => downloadCsv(`${stem}-curve.csv`, data.curve)}>Curve values CSV</button>} />}
          <p className="sensitivity-caption">Shading is an approximate 95% pointwise uncertainty band for the mean adjusted contrast, using a 168-hour dependence adjustment. It is not a prediction interval for an individual hour. Values outside observed support are withheld.</p>
          <details><summary>Curve values and 336-hour uncertainty check</summary><div className="sensitivity-table-wrap"><table><thead><tr><th>°C</th><th>Difference (kWh)</th><th>95% band, 168 h (kWh)</th><th>95% band, 336 h (kWh)</th><th>Nearby hours</th></tr></thead><tbody>{data.curve.map((point) => <tr key={point.temperature}><th>{metric(point.temperature)}</th><td>{metric(point.effect)}</td><td>{metric(point.lower)} to {metric(point.upper)}</td><td>{metric(point.lower336)} to {metric(point.upper336)}</td><td>{number(point.count, 0)}</td></tr>)}</tbody></table></div></details>
        </section>
        <div className="sensitivity-summary">
          <div><span>Selected response</span><strong>{modelName(data.selectedModel)}</strong><small>Chosen on validation dates</small></div>
          <div><span>Held-out test MAE</span><strong>{metric(selectedModel?.test.mae)} <em>kWh</em></strong><small>{number(selectedModel?.test.count, 0)} test hours</small></div>
          <div><span>Training coverage</span><strong>{number(data.splits.train.observedHours, 0)} / {number(data.splits.train.expectedHours, 0)}</strong><small>complete paired hours</small></div>
          <div><span>Supported temperature</span><strong>{metric(data.support.min)} to {metric(data.support.max)} <em>°C</em></strong><small>City weather proxy</small></div>
        </div>
        <details className="study-details"><summary>Model comparison, coverage & residual checks</summary>
        <div className="sensitivity-two-col">
          <section className="analysis-panel"><h2>Temperature support</h2><p>Training and validation hours by temperature bin. Sparse extremes are less reliable even inside the supported range.</p>{support && <AnalysisChart option={support} height={260} label={`${area} development temperature support histogram`} />}
            <details><summary>Monthly temperature support</summary><div className="sensitivity-table-wrap"><table><thead><tr><th>Month</th><th>Hours</th><th>Min °C</th><th>Max °C</th></tr></thead><tbody>{data.support.byMonth.map((row) => <tr key={row.month}><td>{new Intl.DateTimeFormat("en-GB", { month: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2024, row.month - 1, 1)))}</td><td>{number(row.count, 0)}</td><td>{metric(row.min)}</td><td>{metric(row.max)}</td></tr>)}</tbody></table></div></details>
          </section>
          <section className="analysis-panel"><h2>Recorded study periods</h2><p>Chronological splits are fixed in the saved artifact. Each UTC start is inclusive and each end is exclusive. The final period is a retrospective, exploratory evaluation.</p><div className="sensitivity-splits">{(["train", "validation", "test"] as const).map((name) => <div key={name}><span>{name === "test" ? "Held-out evaluation" : name}</span><strong>{splitLabel(data.splits[name])}</strong><small>{number(data.splits[name].observedHours, 0)} / {number(data.splits[name].expectedHours, 0)} paired hours</small></div>)}</div></section>
        </div>
        <section className="analysis-panel"><h2>Model comparison for {area}</h2><p>Validation selected the response; the later test period checks how it held up. Lower MAE is better within this area.</p><div className="sensitivity-table-wrap"><table><thead><tr><th>Model</th><th>Validation MAE (kWh)</th><th>Test MAE (kWh)</th><th>Test RMSE (kWh)</th><th>Test bias (kWh)</th><th>Test hours</th></tr></thead><tbody>{data.models.map((item) => <tr key={item.model} className={item.model === data.selectedModel ? "is-selected" : undefined}><th>{item.label || modelName(item.model)}{item.model === data.selectedModel && <span className="sensitivity-badge">Selected</span>}</th><td>{metric(item.validation.mae)}</td><td>{metric(item.test.mae)}</td><td>{metric(item.test.rmse)}</td><td>{metric(item.test.bias)}</td><td>{number(item.test.count, 0)}</td></tr>)}</tbody></table></div><p className="sensitivity-caption">Scores compare individual hourly household energy observations. Bias is mean observation minus prediction.</p></section>
        <section className="analysis-panel"><h2>Across the five price areas</h2><p>Each area has a different demand scale. These raw MAEs describe within-area performance and should not be read as a league table.</p><div className="sensitivity-table-wrap"><table><thead><tr><th>Area</th><th>Selected model</th><th>Test MAE (kWh)</th><th>Training coverage</th></tr></thead><tbody>{study.areas.map((item) => <tr key={item.area} className={item.area === area ? "is-selected" : undefined}><th><button type="button" className="sensitivity-area-link" onClick={() => onAreaChange(item.area)}>{item.area}</button></th>{item.status === "ok" ? <><td>{modelName(item.selectedModel)}</td><td>{metric(item.models.find((model) => model.model === item.selectedModel)?.test.mae)}</td><td>{number(item.splits.train.observedHours, 0)} / {number(item.splits.train.expectedHours, 0)} h</td></> : <td colSpan={3}>Unavailable: {item.reason}</td>}</tr>)}</tbody></table></div></section>
        <section className="analysis-panel">
          <h2>Residual checks</h2>
          <p>Patterns left in the selected model’s errors show where its calendar and temperature terms do not explain demand. Mean error is observation minus prediction.</p>
          <div className="sensitivity-two-col"><div><h3>Autocorrelation by lag</h3>{acf && <AnalysisChart option={acf} height={245} label={`${area} selected-model residual autocorrelation by lag`} />}</div><div><h3>Mean error by local hour</h3>{byHour && <AnalysisChart option={byHour} height={245} label={`${area} selected-model mean residual by Europe Oslo hour`} />}</div></div>
          <details><summary>Residual values and sample counts</summary>
            <div className="sensitivity-two-col">
              <div className="sensitivity-table-wrap"><table><thead><tr><th>Lag (h)</th><th>Correlation</th><th>Pairs</th></tr></thead><tbody>{data.residuals.acf.map((row) => <tr key={row.lagHours}><td>{row.lagHours}</td><td>{metric(row.correlation, 3)}</td><td>{number(row.pairs, 0)}</td></tr>)}</tbody></table></div>
              <div className="sensitivity-table-wrap"><table><thead><tr><th>Oslo hour</th><th>Mean error (kWh)</th><th>Hours</th></tr></thead><tbody>{data.residuals.byHour.map((row) => <tr key={row.hour}><td>{row.hour}</td><td>{metric(row.mean)}</td><td>{number(row.count, 0)}</td></tr>)}</tbody></table></div>
            </div>
            <div className="sensitivity-table-wrap"><table><thead><tr><th>Oslo month</th><th>Mean error (kWh)</th><th>Hours</th></tr></thead><tbody>{data.residuals.byMonth.map((row) => <tr key={row.month}><td>{new Intl.DateTimeFormat("en-GB", { month: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2024, row.month - 1, 1)))}</td><td>{metric(row.mean)}</td><td>{number(row.count, 0)}</td></tr>)}</tbody></table></div>
          </details>
        </section>
        </details>
        <details className="study-details sensitivity-limits"><summary>Interpretation & study method</summary><p>This is an adjusted association, not evidence that a temperature change causes the displayed demand change. The curve compares temperatures under otherwise identical calendar conditions in an additive model; it does not predict demand for an individual hour.</p><p>Weather is represented by one fixed city proxy per area, not an area-wide average. Seasonal demand and temperature overlap, and unexplained serial structure may remain. Confidence is limited near sparse temperatures. The 336-hour uncertainty sensitivity and seasonal-term check are recorded below.</p><HelpPanel label="Study method and provenance"><div className="sensitivity-method"><p><strong>Seasonal sensitivity:</strong> {data.sensitivity.notes} Maximum curve difference: {metric(data.sensitivity.maxCurveDifference)} kWh, using {data.sensitivity.harmonics} annual harmonics.</p><h3>Protocol</h3><pre>{JSON.stringify(study.protocol, null, 2)}</pre><h3>Area metadata</h3><pre>{JSON.stringify(data.metadata, null, 2)}</pre><h3>Study metadata</h3><pre>{JSON.stringify(study.metadata, null, 2)}</pre></div></HelpPanel></details>
      </> : <div className="diagnostics-state" role="status"><strong>{area} unavailable</strong><span>{selected?.status === "unavailable" ? selected.reason : "This area is absent from the saved study."}</span></div>}
    </>}
  </div>;
}

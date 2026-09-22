"use client";

import { useMemo, useState } from "react";
import type { EChartsCoreOption } from "echarts/core";
import AnalysisChart from "@/components/analysis-chart";
import { HelpPanel } from "@/components/help";
import { Select } from "@/components/ui/select";
import { downloadCsv, downloadJson } from "@/lib/download";
import { number } from "@/lib/api";
import "./demand-peaks.css";

type Peak = { time: string; valueKwh: number; tieCount: number };
type Change = { time: string; previousTime: string; changeKwh: number; tieCount: number };
type Common = {
  query: { start: string; end: string; area?: string; kind: "consumption"; group: "household"; interval: string };
  dataMode: "observed" | "fixture";
  unit: "kWh";
  metadata: Record<string, unknown>;
};
export type AreaPeaks = Common & AreaAnalysis;
type AreaAnalysis = {
  area: string;
  coverage: { expectedHours: number; observedHours: number; excludedHours: number; validRampPairs: number; expectedRampPairs: number };
  summary: { meanKwh: number | null; peak: Peak | null; largestRise: Change | null; largestFall: Change | null };
  duration: { valueKwh: number; hoursAtOrAbove: number; percentAtOrAbove: number }[];
  hourly: { time: string; valueKwh: number | null; changeKwh: number | null }[];
  calculation: Record<string, unknown>;
};
export type RegionalPeaks = Common & RegionalAnalysis;
type RegionalAnalysis = {
  coverage: { expectedHours: number; matchedHours: number; excludedHours: number; byArea: { area: string; observedHours: number; excludedHours: number }[] };
  areas: { area: string; meanKwh: number | null; peak: Peak | null; atCoincidentPeakKwh: number | null }[];
  coincidentPeak: Peak | null;
  sumIndividualPeaksKwh: number | null;
  coincidenceFactor: number | null;
  correlations: { areaA: string; areaB: string; r: number | null; hours: number }[];
  hourly: ({ time: string } & Partial<Record<"NO1" | "NO2" | "NO3" | "NO4" | "NO5", number | null>>)[];
  calculation: Record<string, unknown>;
};

const areaNames = ["NO1", "NO2", "NO3", "NO4", "NO5"] as const;
const colours = ["#176b59", "#3f7eaa", "#d2a83f", "#7775a5", "#9a6558"];

function oslo(value: string | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : new Intl.DateTimeFormat("en-GB", {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    timeZone: "Europe/Oslo", timeZoneName: "short", hourCycle: "h23",
  }).format(date);
}

function frame(xName: string, yName: string): EChartsCoreOption {
  return {
    useUTC: true,
    animation: false,
    grid: { left: 75, right: 24, top: 42, bottom: 75 },
    tooltip: { trigger: "axis" },
    dataZoom: [{ type: "inside" }, { type: "slider", bottom: 12, height: 18 }],
    xAxis: { type: xName === "UTC" ? "time" : "value", name: xName, nameLocation: "middle", nameGap: 28, min: xName === "UTC" ? undefined : 0, max: xName === "UTC" ? undefined : 100, splitNumber: 3, axisLabel: { hideOverlap: true } },
    yAxis: { type: "value", name: yName, nameLocation: "middle", nameGap: 58, scale: true },
  };
}

function ResultDetails({ data, children }: { data: Common; children?: React.ReactNode }) {
  return <HelpPanel label="Coverage & method">
    {children}
    <p>Source: {data.dataMode === "fixture" ? "synthetic fixture" : "published Elhub household consumption"} · hourly kWh · {data.query.start} to {data.query.end} (end excluded, UTC). Peak means observed hourly energy, not instantaneous power or grid capacity. Ties select the earliest UTC hour. Times beside metrics use Europe/Oslo; chart dates use UTC. No seasonal adjustment is applied.</p>
    <p>Download Data & method JSON from Export for full coverage, provenance and calculation definitions.</p>
  </HelpPanel>;
}

function FixtureNote({ mode }: { mode: Common["dataMode"] }) {
  return mode === "fixture" ? <p className="peak-fixture" role="note">Synthetic fixture example · not Norwegian observations</p> : null;
}

export function ExplorePeaksView({ result }: { result: AreaPeaks }) {
  const [display, setDisplay] = useState<"duration" | "changes">("duration");
  const study = result;
  const { coverage, summary, duration, hourly } = study;
  const option = useMemo<EChartsCoreOption>(() => display === "duration" ? {
    ...frame("Hours at or above (%)", "Hourly energy (kWh)"),
    series: [{ type: "line", name: "Demand", showSymbol: duration.length === 1, symbolSize: 9, lineStyle: { width: 2.5, color: colours[0] }, itemStyle: { color: colours[0] }, data: duration.map((row) => [row.percentAtOrAbove, row.valueKwh]) }],
  } : {
    ...frame("UTC", "Change (kWh)"),
    series: [{ type: "line", name: "Hour-to-hour change", showSymbol: false, connectNulls: false, lineStyle: { width: 1.8, color: colours[0] }, itemStyle: { color: colours[0] }, data: hourly.map((row) => [row.time, row.changeKwh]) }],
  }, [display, duration, hourly]);
  const filename = `${study.area}-household-peaks-${result.query.start}-${result.query.end}`;
  return <section className="analysis-panel peak-workspace" aria-label="Household demand peaks">
    <div className="peak-heading">
      <div><h2>{study.area} household demand peaks</h2></div>
      <label>Chart <Select aria-label="Peak demand chart" value={display} onChange={(event) => setDisplay(event.target.value as typeof display)}><option value="duration">Load duration</option><option value="changes">Hourly changes</option></Select></label>
    </div>
    <FixtureNote mode={result.dataMode} />
    {coverage.observedHours === 0 ? <p className="peak-empty" role="status">No observed household hours in this date range. Adjust the dates to inspect peaks.</p> : display === "changes" && coverage.validRampPairs === 0 ? <p className="peak-empty" role="status">No consecutive observed hours are available to calculate a change. Try a wider date range.</p> : <AnalysisChart option={option} height={460} label={`${study.area} household demand ${display === "duration" ? "load duration" : "hourly changes"}`} exports={<>
      <button type="button" onClick={() => downloadCsv(`${filename}-duration.csv`, duration)}>Load duration CSV</button>
      <button type="button" onClick={() => downloadCsv(`${filename}-hourly.csv`, hourly)}>Hourly values CSV</button>
      <button type="button" onClick={() => downloadJson(`${filename}.json`, result)}>Data & method JSON</button>
    </>} />}
    <div className="peak-stats">
      <div><span>Highest hour</span><strong>{number(summary.peak?.valueKwh, 0)} kWh</strong><small>{oslo(summary.peak?.time)}</small></div>
      <div><span>Steepest rise</span><strong>{summary.largestRise ? "+" : ""}{number(summary.largestRise?.changeKwh, 0)} kWh</strong><small>{oslo(summary.largestRise?.time)}</small></div>
      <div><span>Steepest fall</span><strong>{number(summary.largestFall?.changeKwh, 0)} kWh</strong><small>{oslo(summary.largestFall?.time)}</small></div>
    </div>
    <div className="peak-footnote"><span>{number(coverage.observedHours, 0)} / {number(coverage.expectedHours, 0)} observed hours · {number(coverage.validRampPairs, 0)} / {number(coverage.expectedRampPairs, 0)} consecutive pairs</span>
      <ResultDetails data={result}><p>{number(coverage.excludedHours, 0)} hours excluded. Tied maxima: {number(summary.peak?.tieCount, 0)} peak, {number(summary.largestRise?.tieCount, 0)} rise, {number(summary.largestFall?.tieCount, 0)} fall. Duration percentages count hours at or above each threshold, based on observed hours only. Changes require consecutive observed UTC hours; missing hours never become zero or a change.</p></ResultDetails>
    </div>
  </section>;
}

export function RegionalPeaksView({ result }: { result: RegionalPeaks }) {
  const [display, setDisplay] = useState<"absolute" | "relative">("absolute");
  const study = result;
  const { coverage, areas, hourly } = study;
  const unavailableMeans = areas.filter((row) => row.meanKwh == null || row.meanKwh <= 0).map((row) => row.area);
  const option = useMemo<EChartsCoreOption>(() => ({
    ...frame("UTC", display === "absolute" ? "Hourly energy (kWh)" : "% of area mean"),
    color: colours,
    legend: { top: 0, type: "scroll" },
    series: areaNames.map((area, index) => ({
      name: area, type: "line", showSymbol: false, connectNulls: false,
      lineStyle: { width: 1.8 }, itemStyle: { color: colours[index] },
      data: hourly.map((row) => {
        const value = row[area];
        if (value == null || display === "relative" && unavailableMeans.includes(area)) return [row.time, null];
        return [row.time, display === "absolute" ? value : 100 * value / areas[index].meanKwh!];
      }),
    })),
  }), [display, areas, hourly, unavailableMeans]);
  const filename = `regional-household-peaks-${result.query.start}-${result.query.end}`;
  return <section className="analysis-panel peak-workspace" aria-label="Regional household demand peaks">
    <div className="peak-heading">
      <div><h2>Regional peak alignment</h2></div>
      <label>Scale <Select aria-label="Regional demand scale" value={display} onChange={(event) => setDisplay(event.target.value as typeof display)}><option value="absolute">Energy · kWh</option><option value="relative">Area mean · %</option></Select></label>
    </div>
    <FixtureNote mode={result.dataMode} />
    {coverage.matchedHours === 0 ? <p className="peak-empty" role="status">No hours have household observations in all five areas for this range. Choose other dates to compare regions.</p> : <AnalysisChart option={option} height={480} label={`NO1 to NO5 matched household demand ${display === "absolute" ? "in kWh" : "relative to area mean"}`} exports={<>
      <button type="button" onClick={() => downloadCsv(`${filename}-hourly.csv`, hourly)}>Matched hourly CSV</button>
      <button type="button" onClick={() => downloadCsv(`${filename}-areas.csv`, areas.map((row) => ({ area: row.area, meanKwh: row.meanKwh, peakTime: row.peak?.time, peakKwh: row.peak?.valueKwh, atCoincidentPeakKwh: row.atCoincidentPeakKwh })))}>Area peaks CSV</button>
      <button type="button" onClick={() => downloadJson(`${filename}.json`, result)}>Data & method JSON</button>
    </>} />}
    {display === "relative" && unavailableMeans.length > 0 && coverage.matchedHours > 0 && <p className="peak-unavailable" role="status">Relative shape unavailable for {unavailableMeans.join(", ")} because its matched-hour mean is zero or missing. Select Energy · kWh for the observed values.</p>}
    <div className="peak-stats peak-stats-regional">
      <div><span>Combined highest hour</span><strong>{number(study.coincidentPeak?.valueKwh, 0)} kWh</strong><small>{oslo(study.coincidentPeak?.time)}</small></div>
      <div><span>Peak alignment</span><strong>{study.coincidenceFactor == null ? "—" : `${number(study.coincidenceFactor * 100, 1)}%`}</strong><small>Combined peak / sum of area peaks</small></div>
    </div>
    <div className="peak-footnote"><span>{number(coverage.matchedHours, 0)} / {number(coverage.expectedHours, 0)} hours matched across all areas</span>
      <ResultDetails data={result}>
        <p>{number(coverage.excludedHours, 0)} unmatched {coverage.excludedHours === 1 ? "hour" : "hours"} excluded from comparisons. Relative curves divide each area by its matched-hour mean, when positive. Peak alignment describes observed coincidence; it does not imply transfers or capacity.</p>
        <div className="peak-table-scroll" role="region" aria-label="Regional coverage details" tabIndex={0}><table><thead><tr><th>Area</th><th>Observed</th><th>Excluded</th></tr></thead><tbody>{coverage.byArea.map((row) => <tr key={row.area}><th>{row.area}</th><td>{number(row.observedHours, 0)}</td><td>{number(row.excludedHours, 0)}</td></tr>)}</tbody></table></div>
        <h3>Matched-hour correlations</h3>
        <p>Raw Pearson correlation describes co-movement; it does not identify direct transfers or cause. A constant series or fewer than two matched hours leaves it undefined.</p>
        <div className="peak-table-scroll" role="region" aria-label="Matched-hour correlations" tabIndex={0}><table><thead><tr><th>Areas</th><th>Correlation</th><th>Hours</th></tr></thead><tbody>{study.correlations.map((row) => <tr key={`${row.areaA}-${row.areaB}`}><th>{row.areaA}–{row.areaB}</th><td>{number(row.r, 2)}</td><td>{number(row.hours, 0)}</td></tr>)}</tbody></table></div>
      </ResultDetails>
    </div>
    <details className="peak-details"><summary>Area peaks</summary><div className="peak-table-scroll" role="region" aria-label="Area peak comparison" tabIndex={0}><table><thead><tr><th>Area</th><th>Own peak (kWh)</th><th>Peak time · Oslo</th><th>At combined peak (kWh)</th></tr></thead><tbody>{areas.map((row) => <tr key={row.area}><th>{row.area}</th><td>{number(row.peak?.valueKwh, 0)}</td><td>{oslo(row.peak?.time)}</td><td>{number(row.atCoincidentPeakKwh, 0)}</td></tr>)}</tbody></table></div></details>
  </section>;
}

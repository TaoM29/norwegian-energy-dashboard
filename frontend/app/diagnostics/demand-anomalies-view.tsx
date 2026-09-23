"use client";

import { useEffect, useMemo, useState } from "react";
import type { EChartsCoreOption } from "echarts/core";

import { StudyError } from "@/components/study-error";
import AnalysisChart from "@/components/analysis-chart";
import { ExportMenu } from "@/components/export-menu";
import { HelpTip } from "@/components/help";
import { Select } from "@/components/ui/select";
import { ApiError, areas, getJson, number } from "@/lib/api";
import { downloadCsv } from "@/lib/download";
import { displayJson, formatDisplayValue } from "@/lib/number-format";
import "./demand-anomalies.css";

type RecordValue = Record<string, unknown>;
type Candidate = {
  id: string;
  start: string;
  endExclusive: string;
  peakTime: string;
  direction: "high" | "low";
  hours: number;
  peakScore: number;
  peakActual: number;
  peakExpected: number;
  peakTemperature: number | null;
};
type WindowRow = {
  time: string;
  actual: number | null;
  temperature: number | null;
  rawExpected: number | null;
  expected: number | null;
  lower: number | null;
  upper: number | null;
  residual: number | null;
  score: number | null;
  flagged: boolean;
  status: string;
  localDate: string;
  localHour: number;
};
type AreaStudy = {
  area: string;
  status: "ok" | "unavailable";
  reason?: string;
  selectedModel?: string;
  selection?: RecordValue;
  splits?: RecordValue;
  calibration?: RecordValue;
  coverage?: RecordValue;
  summary?: RecordValue;
  diagnostics?: RecordValue;
  metadata?: RecordValue;
  candidates?: Candidate[];
  candidateLimit?: number;
  totalCandidates?: number;
};
type Study = {
  schemaVersion: number;
  id: string;
  createdAt: string;
  dataMode: "observed" | "fixture";
  protocol: RecordValue;
  metadata: RecordValue;
  areas: { area: string; status: string; reason?: string; summary?: RecordValue }[];
  selectedArea: AreaStudy;
  selection: { candidate: Candidate | null; rows: WindowRow[]; peers: unknown };
};

function object(value: unknown): RecordValue {
  return value && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : {};
}

function rows(value: unknown): RecordValue[] {
  return Array.isArray(value) ? value.filter((item): item is RecordValue =>
    !!item && typeof item === "object" && !Array.isArray(item)) : [];
}

function numeric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function metric(value: unknown, digits = 1): string {
  const parsed = numeric(value);
  return parsed == null ? "Unavailable" : number(parsed, digits);
}

function signedMetric(value: unknown): string {
  const parsed = numeric(value);
  return parsed == null ? "Unavailable" : `${parsed > 0 ? "+" : ""}${metric(parsed)}`;
}

function count(value: unknown): string {
  const parsed = numeric(value);
  return parsed == null ? "Unavailable" : number(parsed, 0);
}

function localTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat("en-GB", {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    timeZone: "Europe/Oslo", hourCycle: "h23",
  }).format(date);
}

function chartOption(windowRows: WindowRow[]): EChartsCoreOption {
  const band = windowRows.map((row) => [row.time, row.lower != null && row.upper != null ? row.upper - row.lower : null]);
  const flagged = windowRows.filter((row) => row.flagged && row.actual != null);
  return {
    useUTC: true,
    color: ["#176b59", "#3f7eaa", "#c55252"],
    tooltip: { trigger: "axis" },
    legend: { type: "scroll", top: 2, data: ["Expected demand", "Observed demand", "Flagged hours"] },
    grid: { left: 70, right: 20, top: 46, bottom: 68 },
    dataZoom: [{ type: "inside" }, { type: "slider", bottom: 8, height: 20 }],
    xAxis: { type: "time", axisLabel: { hideOverlap: true } },
    yAxis: { type: "value", name: "kWh", scale: true },
    series: [
      { type: "line", name: "Calibration reference lower", data: windowRows.map((row) => [row.time, row.lower]),
        stack: "reference-band", symbol: "none", lineStyle: { opacity: 0 }, itemStyle: { opacity: 0 }, silent: true,
        tooltip: { show: false } },
      { type: "line", name: "Calibration reference band", data: band, stack: "reference-band", symbol: "none",
        lineStyle: { opacity: 0 }, itemStyle: { opacity: 0 }, areaStyle: { color: "rgba(63,126,170,.17)" }, silent: true,
        tooltip: { show: false } },
      { type: "line", name: "Expected demand", data: windowRows.map((row) => [row.time, row.expected]),
        showSymbol: false, connectNulls: false, lineStyle: { width: 2, color: "#3f7eaa" }, itemStyle: { color: "#3f7eaa" } },
      { type: "line", name: "Observed demand", data: windowRows.map((row) => [row.time, row.actual]),
        showSymbol: false, connectNulls: false, lineStyle: { width: 2.5, color: "#176b59" }, itemStyle: { color: "#176b59" } },
      { type: "scatter", name: "Flagged hours", data: flagged.map((row) => [row.time, row.actual]), symbolSize: 9,
        itemStyle: { color: "#c55252" } },
    ],
  } as EChartsCoreOption;
}

function PeerDays({ peers }: { peers: unknown }) {
  const data = object(peers);
  const candidates = rows(data.days);
  const average = (items: RecordValue[], key: string): number | null => {
    const finite = items.map((item) => numeric(item[key])).filter((value): value is number => value != null);
    return finite.length ? finite.reduce((sum, value) => sum + value, 0) / finite.length : null;
  };
  if (data.status === "unavailable" || !candidates.length) return <p>
    {text(data.reason) || "No comparable pre-evaluation peer days are available for this selected window."}
    {numeric(data.excludedDstDays) != null && ` ${count(data.excludedDstDays)} daylight-saving dates were excluded.`}
  </p>;
  return <>
    <HelpTip label="Matching details" iconOnly>{count(data.targetHours)} target hours on {text(data.targetDate) || "the selected local date"}; {count(data.excludedDstDays)} daylight-saving dates excluded.</HelpTip>
    <div className="demand-anomalies-table-wrap" role="region" aria-label="Comparable peer days" tabIndex={0}>
      <table>
        <caption>Pre-evaluation observed peer days · context only, not confirmed normal controls</caption>
        <thead><tr><th scope="col">Local date</th><th scope="col">Comparable hours</th><th scope="col">Mean demand (kWh)</th><th scope="col">Mean temperature (°C)</th><th scope="col">Temperature difference (°C)</th><th scope="col">Season distance</th></tr></thead>
        <tbody>{candidates.map((peer, index) => <tr key={`${text(peer.date)}-${index}`}>
          <th scope="row">{text(peer.date) || "Unavailable"}</th>
          <td>{count(rows(peer.rows).length)}</td>
          <td>{metric(average(rows(peer.rows), "actual"))}</td>
          <td>{metric(average(rows(peer.rows), "temperature"))}</td>
          <td>{metric(peer.temperatureDifference)} °C</td>
          <td>{count(peer.seasonDistance)} days</td>
        </tr>)}</tbody>
      </table>
    </div>
    <details><summary>Hourly peer and selected-day observations</summary>
      {[{ date: text(data.targetDate), rows: data.targetRows }, ...candidates].map((peer, index) => <div key={`${text(peer.date)}-${index}`}>
        <h3>{index === 0 ? "Selected day" : "Peer day"}: {text(peer.date)}</h3>
        <div className="demand-anomalies-table-wrap" role="region" aria-label={`${text(peer.date)} hourly observations`} tabIndex={0}>
          <table><thead><tr><th scope="col">Oslo hour</th><th scope="col">Observed kWh</th><th scope="col">Temperature °C</th></tr></thead>
            <tbody>{rows(peer.rows).map((row, hourIndex) => <tr key={`${text(row.time)}-${hourIndex}`}>
              <th scope="row">{count(row.localHour)}</th><td>{metric(row.actual)}</td><td>{metric(row.temperature)}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </div>)}
    </details>
  </>;
}

export default function DemandAnomaliesView({
  area, candidate, onAreaChange, onCandidateChange,
}: {
  area: string;
  candidate: string;
  onAreaChange: (area: string) => void;
  onCandidateChange: (candidate: string) => void;
}) {
  const [study, setStudy] = useState<Study | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [missing, setMissing] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ area });
    if (candidate) params.set("candidate", candidate);
    setLoading(true);
    setStudy(null);
    setError("");
    setMissing(false);
    getJson<Study>(`/api/diagnostics/demand-anomalies?${params}`, controller.signal)
      .then((result) => {
        if (result.schemaVersion !== 1 || !Array.isArray(result.areas) || !result.selectedArea || !result.selection) {
          throw new Error("The saved demand-anomaly study could not be read.");
        }
        setStudy(result);
      })
      .catch((problem: unknown) => {
        if (controller.signal.aborted) return;
        setStudy(null);
        setMissing(problem instanceof ApiError && problem.status === 404 && /no saved/i.test(problem.message));
      setError(problem instanceof Error ? problem.message : "No saved demand-anomaly study is available.");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [area, candidate, retry]);

  const selected = study?.selectedArea;
  const summary = object(selected?.summary);
  const coverage = object(selected?.coverage);
  const testCoverage = object(coverage.test);
  const testStatus = object(testCoverage.statusCounts);
  const calibration = object(selected?.calibration);
  const groupSupport = object(calibration.groupSupport);
  const modelSelection = object(selected?.selection);
  const candidates = selected?.status === "ok" && Array.isArray(selected.candidates) ? selected.candidates : [];
  const totalCandidates = numeric(selected?.totalCandidates) ?? numeric(summary.episodes);
  const windowRows = Array.isArray(study?.selection.rows) ? study.selection.rows : [];
  const chosen = study?.selection.candidate || null;
  const option = useMemo(() => chartOption(windowRows), [windowRows]);
  const fileStem = `demand-anomalies-${area.toLowerCase()}${chosen ? `-${chosen.id}` : "-reference"}`;

  return <div className="demand-anomalies-view">
    <div className="demand-anomalies-intro">
      <div>
        <h2>Unusual household demand</h2>
        <HelpTip label="Flag meaning" iconOnly>Expected demand accounts for hour, season and temperature. Flags are candidates for review, not confirmed events.</HelpTip>
      </div>
      <label>Price area
        <Select aria-label="Demand anomalies price area" value={area} onChange={(event) => onAreaChange(event.target.value)}>
          {Object.entries(areas).map(([code, name]) => <option key={code} value={code}>{code} · {name}</option>)}
        </Select>
      </label>
    </div>
    {loading && <div className="diagnostics-state" role="status">Loading saved demand-anomaly study…</div>}
    {error && <>
      <StudyError message={error} missing={missing} onRetry={() => setRetry((value) => value + 1)} />
      {candidate && !missing && <button type="button" onClick={() => onCandidateChange("")}>Clear selected candidate</button>}
    </>}
    {study && !loading && <>
      <div className="demand-anomalies-study-strip">
        <span>{study.dataMode === "fixture" ? "Fixture demonstration" : "Observed-data study"}</span>
        <span>Saved {localTime(study.createdAt)}</span>
        <ExportMenu label="Export anomaly study">
          <a href="/api/diagnostics/demand-anomalies/artifact" download>Complete artifact JSON</a>
          <button type="button" onClick={() => downloadCsv(`${fileStem}-window.csv`, windowRows)}>Selected window CSV</button>
          <button type="button" onClick={() => downloadCsv(`demand-anomalies-${area.toLowerCase()}-candidates.csv`, candidates)}>Ranked candidates CSV</button>
        </ExportMenu>
      </div>
      {selected?.status !== "ok" ? <div className="diagnostics-state" role="status">
        <strong>{area} unavailable</strong><span>{selected?.reason || "This area is absent from the saved study."}</span>
      </div> : <>
        <section className="analysis-panel demand-anomalies-primary" aria-labelledby="anomaly-chart-title">
          <div className="demand-anomalies-heading">
            <div><h2 id="anomaly-chart-title">Observed and expected demand <HelpTip label="Chart interpretation" iconOnly>The shaded .5th–99.5th percentile calibration band is a screening reference, not a prediction or confidence interval. Gaps remain missing; times are UTC.</HelpTip></h2>
              <p>{chosen ? `Window around ${localTime(chosen.peakTime)} Oslo time` : "First week of the saved evaluation period"}</p></div>
          </div>
          {windowRows.length ? <AnalysisChart option={option} height={360} label={`${area} observed and expected household demand around ${chosen ? `candidate ${chosen.id}` : "the first evaluation week"}`} />
            : <div className="diagnostics-state" role="status">No hourly context is available for this selection.</div>}
          <details><summary>Hourly context and coverage status</summary>
            <div className="demand-anomalies-table-wrap" role="region" aria-label="Selected anomaly hourly context" tabIndex={0}><table>
              <thead><tr><th scope="col">UTC hour</th><th scope="col">Observed kWh</th><th scope="col">Expected kWh</th><th scope="col">Temperature °C</th><th scope="col">Score</th><th scope="col">Status</th></tr></thead>
              <tbody>{windowRows.map((row) => <tr key={row.time}><th scope="row">{row.time}</th><td>{metric(row.actual)}</td><td>{metric(row.expected)}</td><td>{metric(row.temperature)}</td><td>{metric(row.score, 2)}</td><td>{row.flagged ? "Flagged" : row.status ? row.status.replaceAll("_", " ") : "Scored"}</td></tr>)}</tbody>
            </table></div>
          </details>
        </section>
        <div className="demand-anomalies-summary">
          <div><span>Scored hours</span><strong>{count(summary.scoredHours)}</strong><small>of {count(summary.expectedHours)} expected in the evaluation period</small></div>
          <div><span>Flagged hours</span><strong>{count(summary.flaggedHours)}</strong></div>
          <div><span>Flag rate · scored hours</span><strong>{numeric(summary.flagRate) == null ? "Unavailable" : `${formatDisplayValue(numeric(summary.flagRate)! * 100, 2)}%`}</strong></div>
          <div><span>Candidate episodes</span><strong>{count(summary.episodes)}</strong></div>
        </div>

        <div className="demand-anomalies-two-col">
          <section className="analysis-panel" aria-labelledby="candidate-list-title">
            <h2 id="candidate-list-title">Ranked candidates · {candidates.length} of {count(totalCandidates)} <HelpTip label="Ranking details" iconOnly>Ranked by peak score. Scores above 1 cross the calibrated side-specific threshold; duration counts consecutive flagged hours.</HelpTip></h2>
            {candidates.length ? <div className="demand-anomalies-table-wrap" role="region" aria-label="Ranked demand anomaly candidates" tabIndex={0}>
              <table><thead><tr><th scope="col">Rank / peak (Oslo)</th><th scope="col">Direction</th><th scope="col">Peak score</th><th scope="col">Duration</th><th scope="col">Actual / expected</th><th scope="col">Temperature</th></tr></thead>
                <tbody>{candidates.map((item, index) => <tr key={item.id} className={chosen?.id === item.id ? "is-selected" : undefined}>
                  <th scope="row"><button type="button" aria-current={chosen?.id === item.id ? "true" : undefined} onClick={() => onCandidateChange(item.id)}>
                    {index + 1}. {localTime(item.peakTime)}</button></th>
                  <td>{item.direction === "high" ? "Above expected" : "Below expected"}</td><td>{metric(item.peakScore, 2)}</td>
                  <td>{count(item.hours)} h</td><td>{metric(item.peakActual)} / {metric(item.peakExpected)} kWh</td>
                  <td>{metric(item.peakTemperature)} °C</td>
                </tr>)}</tbody>
              </table>
            </div> : <p>No flagged episodes were saved for this area.</p>}
          </section>
          <details className="study-details">
            <summary>Comparable observed days</summary>
            <PeerDays peers={study.selection.peers} />
          </details>
        </div>
        <section className="analysis-panel demand-anomalies-details" aria-labelledby="anomaly-method-title">
          <h2 id="anomaly-method-title">Coverage and method <HelpTip label="Study scope" iconOnly>Retrospective scoring uses contemporaneous temperature from one city proxy per area. It is not an operational alarm or a causal estimate.</HelpTip></h2>
          <div className="demand-anomalies-coverage">
            <div><span>Missing demand only</span><strong>{count(testStatus.missing_demand)}</strong></div>
            <div><span>Missing temperature only</span><strong>{count(testStatus.missing_temperature)}</strong></div>
            <div><span>Both inputs missing</span><strong>{count(testStatus.missing_both)}</strong></div>
            <div><span>Unsupported temperature</span><strong>{count(testStatus.unsupported_temperature)}</strong></div>
          </div>
          <HelpTip label="Coverage interpretation" iconOnly>Missing and unsupported hours are coverage gaps, not anomaly scores.</HelpTip>
          <details><summary>Model selection, calendar thresholds and study periods</summary>
            <div className="demand-anomalies-method">
              <p>The expected value adds a {signedMetric(calibration.medianCorrection)} kWh median correction to the raw model fit. The calibration screening band extends {numeric(calibration.lowerWidth) == null ? "Unavailable" : `-${metric(calibration.lowerWidth)}`} kWh below and {numeric(calibration.upperWidth) == null ? "Unavailable" : `+${metric(calibration.upperWidth)}`} kWh above that corrected expectation. It uses {count(calibration.observations)} hourly calibration observations over {count(calibration.distinctDates)} dates; the target tail fraction is {numeric(calibration.tailFraction) == null ? "unavailable" : `${formatDisplayValue(numeric(calibration.tailFraction)! * 100, 1)}%`}.</p>
              <p>Selected expected-demand model: <strong>{selected.selectedModel || "Unavailable"}</strong>. Model choice precedes threshold calibration and the later evaluation period.</p>
              <h3>Validation model comparison</h3>
              <p>{text(modelSelection.rule)} {numeric(modelSelection.selectedSplineKnots) != null ? `Selected spline knots: ${count(modelSelection.selectedSplineKnots)}.` : ""}</p>
              <div className="demand-anomalies-table-wrap" role="region" aria-label="Expected-demand model validation" tabIndex={0}>
                <table><thead><tr><th scope="col">Model</th><th scope="col">MAE kWh</th><th scope="col">RMSE kWh</th><th scope="col">Bias kWh</th><th scope="col">Hours</th></tr></thead>
                  <tbody>{rows(modelSelection.models).map((model, index) => {
                    const score = object(model.validation);
                    return <tr key={`${text(model.model)}-${index}`} className={model.model === selected.selectedModel ? "is-selected" : undefined}>
                      <th scope="row">{text(model.model)}</th><td>{metric(score.mae)}</td><td>{metric(score.rmse)}</td><td>{metric(score.bias)}</td><td>{count(score.count)}</td>
                    </tr>;
                  })}</tbody>
                </table>
              </div>
              <h3>Calendar-group support in calibration</h3>
              <p>Groups describe support and observed flags under the shared area threshold; they are not separate fine-grained thresholds.</p>
              {(["season", "dayType"] as const).map((group) => <div className="demand-anomalies-table-wrap" role="region" aria-label={`${group} calibration support`} tabIndex={0} key={group}>
                <table><caption>{group === "season" ? "Season" : "Local day type"}</caption>
                  <thead><tr><th scope="col">Group</th><th scope="col">Hours</th><th scope="col">Scored</th><th scope="col">Flags</th><th scope="col">Flag rate</th></tr></thead>
                  <tbody>{rows(groupSupport[group]).map((item, index) => <tr key={`${text(item[group])}-${index}`}>
                    <th scope="row">{text(item[group])}</th><td>{count(item.hours)}</td><td>{count(item.scoredHours)}</td><td>{count(item.flaggedHours)}</td>
                    <td>{numeric(item.flagRate) == null ? "Unavailable" : `${formatDisplayValue(numeric(item.flagRate)! * 100, 2)}%`}</td>
                  </tr>)}</tbody>
                </table>
              </div>)}
              <h3>Study periods and input columns</h3>
              <div className="demand-anomalies-table-wrap" role="region" aria-label="Demand anomaly study periods" tabIndex={0}>
                <table><thead><tr><th scope="col">Stage</th><th scope="col">UTC start</th><th scope="col">UTC end</th><th scope="col">Complete hours</th></tr></thead>
                  <tbody>{Object.entries(object(selected.splits)).map(([name, raw]) => {
                    const split = object(raw);
                    return <tr key={name}><th scope="row">{name}</th><td>{text(split.start) || "Unavailable"}</td><td>{text(split.endExclusive) || "Unavailable"}</td><td>{count(split.completeHours)}</td></tr>;
                  })}</tbody>
                </table>
              </div>
              <p>Selected predictors: {Array.isArray(selected.metadata?.featureColumns)
                ? selected.metadata.featureColumns.filter((item): item is string => typeof item === "string").join(", ")
                : "Unavailable"}.</p>
              <h3>Protocol</h3><pre>{displayJson(study.protocol)}</pre>
            </div>
          </details>
        </section>
      </>}
    </>}
  </div>;
}

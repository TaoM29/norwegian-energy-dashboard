"use client";

import { useEffect, useMemo, useState } from "react";
import type { EChartsCoreOption } from "echarts/core";

import { StudyError } from "@/components/study-error";
import AnalysisChart from "@/components/analysis-chart";
import { ExportMenu } from "@/components/export-menu";
import { ApiError, getJson, number } from "@/lib/api";
import { downloadCsv } from "@/lib/download";
import "./demand-changes.css";

type Values = Record<string, unknown>;
type Day = {
  date: string;
  period: string;
  actual: number | null;
  expected: number | null;
  residual: number | null;
  okHours: number;
  expectedHours: number;
  statusCounts: Record<string, number>;
  complete: boolean;
};
type Segment = {
  start: string;
  endExclusive: string;
  days: number;
  meanActual: number | null;
  meanExpected: number | null;
  meanResidual: number | null;
  medianResidual: number | null;
  q1Residual: number | null;
  q3Residual: number | null;
  residualDistribution: number[];
};
type Candidate = {
  date: string;
  before: Segment;
  after: Segment;
  deltaResidualKwh: number;
  standardizedDelta: number | null;
};
type Primary = {
  status: string;
  detected: boolean;
  score: number | null;
  pValue: number | null;
  thresholdApprox95: number | null;
  candidate: Candidate | null;
  calibrationScaleKwh: number | null;
  eligibleSplits: number;
  testRuns: Values[];
};
type Study = {
  schemaVersion: number;
  id: string;
  createdAt: string;
  dataMode: "observed" | "fixture";
  area: string;
  status: string;
  reason?: string;
  dailyRows: Day[];
  primary: Primary;
  coverage: {
    calibration: Values;
    test: { expectedDays: number; completeDays: number; incompleteDays: number; expectedHours: number; okHours: number; statusCounts: Record<string, number> };
  };
  sensitivities: Values[];
  controlledValidation: Values;
  metadata: Values;
  protocol: Values;
};

const endpoint = "/api/diagnostics/demand-changes";

function value(input: unknown): string {
  return typeof input === "string" ? input : "";
}

function finite(input: unknown): number | null {
  return typeof input === "number" && Number.isFinite(input) ? input : null;
}

function metric(input: unknown, digits = 1): string {
  const parsed = finite(input);
  return parsed == null ? "Unavailable" : number(parsed, digits);
}

function signed(input: unknown, digits = 1): string {
  const parsed = finite(input);
  return parsed == null ? "Unavailable" : `${parsed > 0 ? "+" : ""}${number(parsed, digits)}`;
}

function dayLabel(date: string): string {
  const parsed = new Date(`${date.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(parsed.valueOf()) ? date : new Intl.DateTimeFormat("en-GB", {
    day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
  }).format(parsed);
}

function savedLabel(date: string): string {
  const parsed = new Date(date);
  return Number.isNaN(parsed.valueOf()) ? date : new Intl.DateTimeFormat("en-GB", {
    day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
  }).format(parsed);
}

function timelineOption(days: Day[], candidate: Candidate | null, detected: boolean): EChartsCoreOption {
  return {
    useUTC: true,
    tooltip: { trigger: "axis", valueFormatter: (value: unknown) => typeof value === "number" ? `${number(value, 1)} kWh` : "Unavailable" },
    grid: { left: 72, right: 24, top: 28, bottom: 62 },
    dataZoom: [{ type: "inside" }, { type: "slider", bottom: 8, height: 20 }],
    xAxis: { type: "time", axisLabel: { hideOverlap: true } },
    yAxis: { type: "value", name: "kWh", scale: true },
    series: [{
      type: "line", name: "Daily mean residual", showSymbol: false, connectNulls: false,
      lineStyle: { width: 2, color: "#176b59" }, itemStyle: { color: "#176b59" },
      data: days.map((row) => [`${row.date}T12:00:00Z`, row.complete ? row.residual : null]),
      markLine: {
        symbol: "none", silent: true, label: { show: true, position: "insideEndTop" },
        data: [
          { name: "Zero residual", yAxis: 0, lineStyle: { color: "#607069", type: "dashed", width: 1.5 }, label: { formatter: "Zero" } },
          ...(candidate ? [{ name: detected ? "Candidate change" : "Unconfirmed split", xAxis: `${candidate.date}T00:00:00Z`, lineStyle: { color: "#a87722", type: "dashed" as const, width: 2 }, label: { formatter: detected ? "Candidate" : "Unconfirmed" } }] : []),
        ],
      },
    }],
  } as EChartsCoreOption;
}

function distributionOption(candidate: Candidate): EChartsCoreOption {
  const before = candidate.before.residualDistribution;
  const after = candidate.after.residualDistribution;
  const all = [...before, ...after];
  const low = Math.min(...all);
  const high = Math.max(...all);
  const width = Math.max((high - low) / 12, .01);
  const bins = Array.from({ length: 12 }, (_, index) => low + (index + .5) * width);
  const counts = (values: number[]) => bins.map((_, index) => values.filter((item) => {
    const bin = Math.min(11, Math.max(0, Math.floor((item - low) / width)));
    return bin === index;
  }).length);
  const labels = [`Before · ${before.length} days`, `After · ${after.length} days`];
  return {
    tooltip: { trigger: "axis", valueFormatter: (v: unknown) => typeof v === "number" ? `${number(v, 1)}% of days` : "Unavailable" },
    legend: { top: 2, data: labels },
    grid: { left: 58, right: 20, top: 72, bottom: 52 },
    xAxis: { type: "category", name: "Mean hourly residual (kWh)", nameLocation: "middle", nameGap: 31,
      data: bins.map((mid) => number(mid, 1)), axisLabel: { hideOverlap: true } },
    yAxis: { type: "value", name: "% of days" },
    series: [
      { type: "bar", name: labels[0], data: counts(before).map((count) => count / before.length * 100), itemStyle: { color: "#3f7eaa" }, barMaxWidth: 22 },
      { type: "bar", name: labels[1], data: counts(after).map((count) => count / after.length * 100), itemStyle: { color: "#176b59" }, barMaxWidth: 22 },
    ],
  } as EChartsCoreOption;
}

export default function DemandChangesView() {
  const [study, setStudy] = useState<Study | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [missing, setMissing] = useState(false);
  const [retry, setRetry] = useState(0);
  const [chart, setChart] = useState<"timeline" | "distribution">("timeline");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setStudy(null);
    setError("");
    setMissing(false);
    setChart("timeline");
    getJson<Study>(endpoint, controller.signal)
      .then((result) => {
        if (result.schemaVersion !== 1 || result.area !== "NO1" || (result.status === "ok" && (!Array.isArray(result.dailyRows) || !result.primary))) {
          throw new Error("The saved demand-change study could not be read.");
        }
        setStudy(result);
      })
      .catch((problem: unknown) => {
        if (controller.signal.aborted) return;
        setStudy(null);
        setMissing(problem instanceof ApiError && problem.status === 404 && /no saved/i.test(problem.message));
      setError(problem instanceof Error ? problem.message : "No saved demand-change study is available.");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [retry]);

  const testDays = useMemo(() => study?.status === "ok" && Array.isArray(study.dailyRows) ? study.dailyRows.filter((day) => day.period === "test") : [], [study]);
  const calibrationDays = study?.status === "ok" && Array.isArray(study.dailyRows) ? study.dailyRows.filter((day) => day.period === "calibration") : [];
  const candidate = study?.primary?.candidate || null;
  const detected = Boolean(study?.primary?.detected);
  const timeline = useMemo(() => timelineOption(testDays, candidate, detected), [testDays, candidate, detected]);
  const distribution = useMemo(() => candidate ? distributionOption(candidate) : null, [candidate]);
  const coverage = study?.coverage?.test;
  const inconclusive = study?.status !== "ok" || study?.primary?.status !== "ok";
  const controlRows = Array.isArray(study?.controlledValidation?.summary)
    ? study.controlledValidation.summary.filter((row): row is Values => Boolean(row && typeof row === "object" && !Array.isArray(row)))
    : [];
  const noChangeControls = controlRows.filter((row) => row.scenario === "no-change");
  const worstFalseAlarm = noChangeControls.reduce<Values | null>((worst, row) =>
    (finite(row.falseAlarmRate ?? row.detectionRate) ?? 0) > (finite(worst?.falseAlarmRate ?? worst?.detectionRate) ?? 0) ? row : worst, null);
  const incompleteDates = testDays.filter((day) => !day.complete).map((day) => day.date);
  const savedPeriod = testDays.length ? `${testDays[0].date}–${testDays[testDays.length - 1].date} UTC` : "2025 UTC evaluation";
  const calibrationPeriod = calibrationDays.length ? `${calibrationDays[0].date}–${calibrationDays[calibrationDays.length - 1].date}` : "saved calibration period";
  const sensitive = candidate && study?.sensitivities.some((item) =>
    typeof item.detected === "boolean" && (item.detected !== detected || item.candidateDate !== candidate.date));

  return <div className="demand-changes-view">
    <div className="demand-changes-intro">

      <h2>Persistent demand changes</h2>
      <p>NO1 household demand after calendar and temperature adjustment. A saved retrospective study.</p>
    </div>
    {loading && <div className="diagnostics-state" role="status">Loading saved demand-change study…</div>}
    {error && <>
      <StudyError message={error} missing={missing} onRetry={() => setRetry((value) => value + 1)} />
    </>}
    {study?.status === "unavailable" && !loading && <div className="diagnostics-state" role="status">
      <strong>Saved study unavailable</strong><span>{study.reason || "The fixed NO1 study could not be evaluated with the saved inputs."}</span>
    </div>}
    {study?.status === "ok" && !loading && <>
      <div className="demand-changes-strip">
        <span>{study.dataMode === "fixture" ? "Fixture demonstration" : "Observed-data study"}</span>
        <span>NO1 · {savedPeriod}</span><span>Saved {savedLabel(study.createdAt)}</span>
        <ExportMenu label="Export demand-change study">
          <a href={`${endpoint}/artifact`} download>Complete artifact JSON</a>
          <button type="button" onClick={() => downloadCsv("demand-changes-no1-daily.csv", study.dailyRows)}>Daily values CSV</button>
        </ExportMenu>
      </div>
      <section className="demand-changes-result" aria-label="Demand-change finding">
        <div>
          <span className="demand-changes-label">2025 finding · {metric(coverage?.completeDays, 0)} of {metric(coverage?.expectedDays, 0)} complete UTC days</span>
          <strong>{inconclusive ? "This study is inconclusive" : candidate && detected ? `Strongest exploratory split near ${dayLabel(candidate.date)}` : candidate ? `Best split near ${dayLabel(candidate.date)} remains unconfirmed` : "No eligible change split"}</strong>
          <p>{inconclusive
            ? "The saved evaluation did not meet its coverage or detection requirements. Inspect coverage and method below before interpreting the timeline."
            : candidate && detected
              ? "This split crosses the exploratory bootstrap reference. It does not confirm a structural break or its cause."
              : "The strongest eligible split did not exceed the saved bootstrap threshold. It is shown for context, not as a detected change. This does not establish that demand was unchanged."}</p>
          {(finite(worstFalseAlarm?.falseAlarmRate ?? worstFalseAlarm?.detectionRate) ?? 0) > .05 && <p className="demand-changes-control-warning">Calibration limit: {metric(worstFalseAlarm?.detections, 0)} of {metric(worstFalseAlarm?.replications, 0)} runs were flagged ({number((finite(worstFalseAlarm?.falseAlarmRate ?? worstFalseAlarm?.detectionRate) ?? 0) * 100, 1)}%) under strong serial dependence with no actual change. This exceeds the nominal 5% target.</p>}
          {sensitive && <p>Sensitivity checks change the date or remove the threshold crossing. The finding depends on the resampling, coverage and baseline assumptions.</p>}
        </div>
        {candidate && !inconclusive && <div className="demand-changes-effect">
          <span className="demand-changes-label">After − before</span>
          <strong>{signed(candidate.deltaResidualKwh)} kWh</strong>
          <small>Mean hourly residual · descriptive {detected ? "after selection" : "unconfirmed split"}</small>
        </div>}
      </section>
      <section className="analysis-panel demand-changes-primary" aria-labelledby="demand-changes-chart-title">
        <div className="demand-changes-heading">
          <div><h2 id="demand-changes-chart-title">{chart === "timeline" ? "Daily demand difference" : "Before and after distributions"}</h2>
            <p>{chart === "timeline" ? "Observed minus expected · daily mean of complete UTC days · kWh" : "Share of days in each residual range · common bins · unequal period lengths"}</p></div>
          {candidate && !inconclusive && <div className="demand-changes-chart-choices" aria-label="Change chart view">
            <button type="button" aria-pressed={chart === "timeline"} onClick={() => setChart("timeline")}>Timeline</button>
            <button type="button" aria-pressed={chart === "distribution"} onClick={() => setChart("distribution")}>Before & after</button>
          </div>}
        </div>
        {testDays.length ? <AnalysisChart
          option={chart === "distribution" && distribution ? distribution : timeline}
          height={350}
          label={chart === "distribution" && candidate ? "NO1 before and after distributions of 2025 daily mean residuals" : "NO1 2025 daily mean household-demand residuals with zero baseline and possible change"}
        /> : <div className="diagnostics-state" role="status">No saved daily observations are available for the 2025 evaluation.</div>}
        <p className="demand-changes-caption">{chart === "distribution"
          ? "Percentages account for unequal period lengths. These distributions describe the selected split; they do not establish its cause or certainty."
          : <>Gaps are incomplete days, not zero residuals. {candidate ? `The dashed split line is ${detected ? "a threshold-crossing exploratory candidate" : "unconfirmed"}. Before/after differences are descriptive; no confidence interval or causal claim is supplied.` : "No split line or before/after estimate is shown without an eligible candidate."}</>}</p>
        {incompleteDates.length > 0 && <p className="demand-changes-caption">Incomplete UTC days: {incompleteDates.length <= 6 ? incompleteDates.join(", ") : `${incompleteDates.slice(0, 6).join(", ")} and ${incompleteDates.length - 6} more`}. Their missing or unsupported hours are shown in the daily table.</p>}
        {candidate && !inconclusive && <details><summary>Before and after estimates</summary>
          <div className="demand-changes-table-wrap" role="region" aria-label="Demand-change before and after estimates" tabIndex={0}>
            <table><thead><tr><th scope="col">Period (UTC)</th><th scope="col">Complete days</th><th scope="col">Mean hourly actual kWh</th><th scope="col">Mean hourly expected kWh</th><th scope="col">Mean hourly residual kWh</th><th scope="col">Median daily residual kWh</th><th scope="col">Middle 50% kWh</th></tr></thead>
              <tbody>{([candidate.before, candidate.after] as Segment[]).map((segment, index) => <tr key={index}>
                <th scope="row">{index === 0 ? "Before" : "After"} · {segment.start} to {segment.endExclusive} exclusive</th>
                <td>{metric(segment.days, 0)}</td><td>{metric(segment.meanActual)}</td><td>{metric(segment.meanExpected)}</td><td>{signed(segment.meanResidual)}</td><td>{signed(segment.medianResidual)}</td><td>{signed(segment.q1Residual)} to {signed(segment.q3Residual)}</td>
              </tr>)}</tbody>
            </table>
          </div>
        </details>}
        <details><summary>Daily values and coverage</summary>
          <div className="demand-changes-table-wrap" role="region" aria-label="Saved daily demand-change values" tabIndex={0}>
            <table><thead><tr><th scope="col">UTC date</th><th scope="col">Mean hourly observed kWh</th><th scope="col">Mean hourly expected kWh</th><th scope="col">Mean hourly residual kWh</th><th scope="col">Complete hours</th><th scope="col">Status</th></tr></thead>
              <tbody>{testDays.map((day) => <tr key={day.date}><th scope="row">{day.date}</th><td>{metric(day.actual)}</td><td>{metric(day.expected)}</td><td>{signed(day.residual)}</td><td>{metric(day.okHours, 0)} / {metric(day.expectedHours, 0)}</td><td>{day.complete ? "Complete" : `Incomplete · ${Object.entries(day.statusCounts || {}).filter(([status]) => status !== "ok").map(([status, count]) => `${status.replaceAll("_", " ")} ${count}`).join(", ") || "coverage gap"}`}</td></tr>)}</tbody>
            </table>
          </div>
        </details>
      </section>
      <section className="analysis-panel" aria-labelledby="demand-changes-method-title">
        <h2 id="demand-changes-method-title">How to read this study</h2>
        <p>One retrospective split, with at least 28 complete days on each side. Review the assumptions and sensitivity checks before interpreting it.</p>
        <details><summary>Detection policy and validation</summary>
          <div className="demand-changes-detail-copy">
            <p>Selected split score: <strong>{metric(study.primary.score, 2)}</strong>. 95th percentile of bootstrap maxima: <strong>{metric(study.primary.thresholdApprox95, 2)}</strong>. Bootstrap exceedance estimate: <strong>{metric(study.primary.pValue, 3)}</strong>. Eligible splits: <strong>{metric(study.primary.eligibleSplits, 0)}</strong>.</p>
            <p>The threshold comes from block resampling of {calibrationPeriod} calibration residuals. Repeating the maximum over every eligible split in each bootstrap draw accounts for searching across dates. Synthetic controls evaluate its false-alarm behavior; they do not set the threshold. The split date is the first day after the selected boundary. A location or magnitude selected after looking at the data does not carry a separate confidence interval.</p>
            {noChangeControls.length > 0 && <p>Independent synthetic no-change controls measure false-alarm behavior under the saved assumptions. Their observed rates do not guarantee the same rate for Norwegian demand.</p>}
            {noChangeControls.length > 0 && <div className="demand-changes-table-wrap" role="region" aria-label="No-change control false alarms" tabIndex={0}>
              <table><thead><tr><th scope="col">Serial correlation</th><th scope="col">Flagged runs</th><th scope="col">False-alarm rate</th></tr></thead>
                <tbody>{noChangeControls.map((row, index) => <tr key={`${value(row.scenario)}-${index}`}><th scope="row">ρ = {metric(row.rho, 2)}</th><td>{metric(row.detections, 0)} / {metric(row.replications, 0)}</td><td>{finite(row.falseAlarmRate ?? row.detectionRate) == null ? "Unavailable" : `${number((finite(row.falseAlarmRate ?? row.detectionRate) ?? 0) * 100, 1)}%`}</td></tr>)}</tbody>
              </table>
            </div>}
            {controlRows.length > noChangeControls.length && <p>Known-shift and gradual-drift control results are in the complete artifact. A gradual trend or a changed baseline can also trigger this scan; a candidate does not prove an abrupt structural break.</p>}
            <p>Changes in input coverage and source revisions can change the result. External events may offer context but cannot establish the cause. Forecast-error drift and online alerts are outside this saved demand study.</p>
            <h3>Study protocol</h3><pre>{JSON.stringify(study.protocol, null, 2)}</pre>
            <h3>Provenance</h3><pre>{JSON.stringify(study.metadata, null, 2)}</pre>
          </div>
        </details>
        <details><summary>Sensitivity and coverage checks</summary>
          <div className="demand-changes-detail-copy"><p>Gap rules, baseline revisions, and alternate settings may shift or remove a candidate. These saved checks are supporting diagnostics, not independent confirmations.</p></div>
          <div className="demand-changes-table-wrap" role="region" aria-label="Demand-change sensitivity checks" tabIndex={0}>
            <table><thead><tr><th scope="col">Check</th><th scope="col">Selected date</th><th scope="col">Split score</th><th scope="col">Bootstrap exceedance</th><th scope="col">After − before kWh</th></tr></thead>
              <tbody>{study.sensitivities.map((item, index) => <tr key={`${value(item.id)}-${index}`}><th scope="row">{value(item.label) || value(item.id) || `Check ${index + 1}`}</th><td>{value(item.candidateDate) ? `${value(item.candidateDate)}${item.detected ? "" : " · unconfirmed"}` : "None"}</td><td>{metric(item.score, 2)}</td><td>{metric(item.pValue, 3)}</td><td>{signed(item.deltaResidualKwh)}</td></tr>)}</tbody>
            </table>
          </div>
          {coverage && <p className="demand-changes-detail-copy">Test coverage: {metric(coverage.okHours, 0)} of {metric(coverage.expectedHours, 0)} hourly pairs; {metric(coverage.incompleteDays, 0)} incomplete UTC days. Missing or unsupported hours are never filled with zero.</p>}
        </details>
      </section>
    </>}
  </div>;
}

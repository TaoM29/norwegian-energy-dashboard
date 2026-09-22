"use client";

import { useMemo, useRef, useState } from "react";
import type { EChartsCoreOption } from "echarts/core";
import AnalysisChart from "@/components/analysis-chart";
import { useTheme } from "@/components/theme-provider";
import { ExportMenu } from "@/components/export-menu";
import { HelpPanel } from "@/components/help";
import { Select } from "@/components/ui/select";
import { number } from "@/lib/api";
import { downloadCsv, downloadJson } from "@/lib/download";
import "./demand-profiles.css";

type ActualHour = { hour: number; medianKwh: number | null; p10Kwh: number | null; p90Kwh: number | null };
type NormalizedHour = { hour: number; medianPercentDailyMean: number | null; p10PercentDailyMean: number | null; p90PercentDailyMean: number | null };
type ProfileGroup = {
  groupType: "dayType" | "season";
  group: string;
  actualDayCount: number;
  normalizedDayCount: number;
  actual: ActualHour[];
  normalized: NormalizedHour[];
  representative: { date: string; squaredDistance: number } | null;
};
type ObservedDay = {
  date: string;
  dayType: string;
  season: string;
  expectedHours: number;
  selectedHours: number;
  validHours: number;
  profileEligible: boolean;
  normalizedEligible: boolean;
  exclusionReasons: string[];
  meanKwh: number | null;
  totalKwh: number | null;
  hours: { timeUtc: string; timeOslo: string; localHour: number; valueKwh: number | null }[];
};
export type DemandProfilesResponse = {
  query: { area: string; start: string; end: string; kind: "consumption"; group: "household"; interval: string };
  dataMode: "fixture" | "observed";
  unit: "kWh";
  timezone: "Europe/Oslo";
  coverage: {
    expectedHours: number; observedHours: number; excludedHours: number; missingHours: number;
    badQualityHours: number; nonfiniteOrNegativeHours: number; touchedDays: number; expectedDays: number;
    profileEligibleDays: number; boundaryExcludedDays: number; dstExcludedDays: number;
    incompleteExcludedDays: number; zeroMeanDays: number; normalizedEligibleDays: number;
  };
  groups: ProfileGroup[];
  days: ObservedDay[];
  calculation: Record<string, unknown>;
  metadata: Record<string, unknown>;
};

type Grouping = ProfileGroup["groupType"];
type Scale = "actual" | "normalized";
const groupNames: Record<string, string> = {
  weekday: "Weekdays", weekend: "Weekends", DJF: "Winter", MAM: "Spring", JJA: "Summer", SON: "Autumn",
};
const groupColours: Record<string, string> = {
  weekday: "#176b59", weekend: "#3f7eaa", DJF: "#3f7eaa", MAM: "#176b59", JJA: "#a87722", SON: "#7775a5",
};
const groupTokens: Record<string, string> = {
  weekday: "var(--chart-series-1)", weekend: "var(--chart-series-2)", DJF: "var(--chart-series-2)", MAM: "var(--chart-series-1)", JJA: "var(--chart-series-3)", SON: "var(--chart-series-4)",
};
const groupStrokes: Record<string, "solid" | "dashed" | "dotted"> = {
  weekday: "solid", weekend: "dashed", DJF: "solid", MAM: "dashed", JJA: "dotted", SON: "solid",
};
const reasons: Record<string, string> = {
  partialBoundaryDay: "Only part of this Oslo day is in the selected UTC range",
  dst23HourDay: "23-hour daylight-saving day",
  dst25HourDay: "25-hour daylight-saving day",
  incompleteDay: "Missing, invalid, or incomplete hourly observations",
  zeroMeanDay: "Zero daily mean; shape cannot be normalized",
};

function values(row: ActualHour | NormalizedHour, scale: Scale) {
  return scale === "actual"
    ? { median: (row as ActualHour).medianKwh, p10: (row as ActualHour).p10Kwh, p90: (row as ActualHour).p90Kwh }
    : { median: (row as NormalizedHour).medianPercentDailyMean, p10: (row as NormalizedHour).p10PercentDailyMean, p90: (row as NormalizedHour).p90PercentDailyMean };
}

function localTime(value: string) {
  // Preserve the source offset so repeated 02:00 hours on a 25-hour day stay distinguishable.
  return value.replace("T", " ").replace(/:\d\d([+-]\d\d:\d\d)$/, " UTC$1");
}

export function DemandProfilesView({ result }: { result: DemandProfilesResponse }) {
  const { theme } = useTheme();
  const [grouping, setGrouping] = useState<Grouping>("dayType");
  const [scale, setScale] = useState<Scale>("actual");
  const [chosenDate, setChosenDate] = useState("");
  const dayDetails = useRef<HTMLDetailsElement>(null);
  const daySummary = useRef<HTMLElement>(null);
  const groups = result.groups.filter((item) => item.groupType === grouping);
  const selectedDay = result.days.find((day) => day.date === chosenDate) || result.days.find((day) => day.profileEligible) || result.days[0];
  const hasProfiles = groups.some((group) => (scale === "actual" ? group.actualDayCount : group.normalizedDayCount) > 0);
  const filename = `${result.query.area}-daily-demand-profiles-${result.query.start}-${result.query.end}`;
  const rows = useMemo(() => result.groups.flatMap((group) => Array.from({ length: 24 }, (_, hour) => {
    const actual = group.actual[hour];
    const normalized = group.normalized[hour];
    return {
      grouping: group.groupType, group: group.group, localHour: hour,
      actualDays: group.actualDayCount, normalizedDays: group.normalizedDayCount,
      medianKwh: actual?.medianKwh ?? null, p10Kwh: actual?.p10Kwh ?? null, p90Kwh: actual?.p90Kwh ?? null,
      medianPercentDailyMean: normalized?.medianPercentDailyMean ?? null,
      p10PercentDailyMean: normalized?.p10PercentDailyMean ?? null,
      p90PercentDailyMean: normalized?.p90PercentDailyMean ?? null,
    };
  })), [result.groups]);
  const rawRows = useMemo(() => result.days.flatMap((day) => day.hours.map((hour) => ({
    localDate: day.date, dayType: day.dayType, season: day.season,
    profileEligible: day.profileEligible, normalizedEligible: day.normalizedEligible,
    exclusionReasons: day.exclusionReasons.join("; "), ...hour,
  }))), [result.days]);
  function inspectDate(date: string) {
    setChosenDate(date);
    if (dayDetails.current) dayDetails.current.open = true;
    requestAnimationFrame(() => {
      daySummary.current?.focus();
      dayDetails.current?.scrollIntoView({ block: "start" });
    });
  }
  const option = useMemo<EChartsCoreOption>(() => ({
    animation: false,
    grid: { left: 76, right: 20, top: 32, bottom: 58, containLabel: false },
    tooltip: { trigger: "axis", valueFormatter: (value: unknown) => value == null ? "—" : `${number(Number(value), scale === "actual" ? 0 : 1)} ${scale === "actual" ? "kWh" : "% of daily mean"}` },
    xAxis: { type: "category", boundaryGap: false, data: Array.from({ length: 24 }, (_, hour) => String(hour).padStart(2, "0")), name: "Hour · Oslo", nameLocation: "middle", nameGap: 32, axisLabel: { interval: 3, hideOverlap: true, formatter: "{value}:00" } },
    yAxis: { type: "value", min: 0, name: scale === "actual" ? "Hourly energy (kWh)" : "Daily mean (%)", nameLocation: "middle", nameGap: 57, axisLabel: { formatter: (value: number) => Math.abs(value) >= 1e6 ? `${(value / 1e6).toFixed(1)}m` : Math.abs(value) >= 1e3 ? `${Math.round(value / 1e3)}k` : String(value) }, splitLine: { lineStyle: { color: "#e2e8e2" } } },
    series: groups.flatMap((group) => {
      const data = scale === "actual" ? group.actual : group.normalized;
      const band = data.map((row) => values(row, scale));
      const color = groupColours[group.group] || "#9a6558";
      return [
        { type: "line", name: `${groupNames[group.group]} lower`, stack: `band-${group.group}`, data: band.map((point) => point.p10), showSymbol: false, lineStyle: { opacity: 0 }, itemStyle: { opacity: 0 }, tooltip: { show: false }, silent: true },
        { type: "line", name: `${groupNames[group.group]} 10th–90th`, stack: `band-${group.group}`, data: band.map((point) => point.p10 == null || point.p90 == null ? null : point.p90 - point.p10), showSymbol: false, lineStyle: { opacity: 0 }, areaStyle: { color, opacity: .13 }, itemStyle: { opacity: 0 }, tooltip: { show: false }, silent: true },
        { type: "line", name: groupNames[group.group] || group.group, data: band.map((point) => point.median), showSymbol: false, connectNulls: false, lineStyle: { color, width: 2.5, type: groupStrokes[group.group] }, itemStyle: { color }, emphasis: { focus: "series" } },
      ];
    }),
  }), [groups, scale]);
  const imageOption: EChartsCoreOption = {
    title: { text: `${result.query.area} · daily household demand${result.dataMode === "fixture" ? " · Synthetic fixture" : ""}`, subtext: `${grouping === "dayType" ? "Weekdays / weekends" : "Seasons"} · ${scale === "actual" ? "kWh" : "% of daily mean"} · ${result.query.start} to ${result.query.end} (UTC end excluded)\nMedian line · 10th–90th percentile between days when n ≥ 5`, left: 26, top: 8, textStyle: { fontSize: 15 }, subtextStyle: { fontSize: 11, lineHeight: 17 } },
    legend: { data: groups.map((group) => groupNames[group.group] || group.group), top: 78, left: 26, type: "scroll" },
    grid: { left: 76, right: 30, top: 120, bottom: 58 },
  };
  const exports = <>
    <button type="button" onClick={() => downloadCsv(`${filename}-profiles.csv`, rows)}>Profile values CSV</button>
    <button type="button" onClick={() => downloadCsv(`${filename}-raw-days.csv`, rawRows)}>Observed days CSV</button>
    <button type="button" onClick={() => downloadJson(`${filename}.json`, result)}>Data & method JSON</button>
  </>;

  return <section className="analysis-panel profile-workspace" aria-label="Daily household demand profiles">
    <header className="profile-heading">
      <div><span className="profile-eyebrow">{result.query.area} · HOUSEHOLD CONSUMPTION</span><h2>Daily demand profiles</h2>
        <p>How demand changes across an Oslo day, compared across observed days.</p></div>
      <div className="profile-choices">
        <label>Compare <Select aria-label="Profile groups" value={grouping} onChange={(event) => setGrouping(event.target.value as Grouping)}><option value="dayType">Weekdays / weekends</option><option value="season">Seasons</option></Select></label>
        <label>Scale <Select aria-label="Profile scale" value={scale} onChange={(event) => setScale(event.target.value as Scale)}><option value="actual">Hourly energy · kWh</option><option value="normalized">Shape · % of daily mean</option></Select></label>
      </div>
    </header>
    {result.dataMode === "fixture" && <p className="profile-fixture" role="note">Synthetic fixture example · not Norwegian observations</p>}
    <div className="profile-legend" aria-label="Displayed profile groups">{groups.map((group) => <div key={group.group} className="profile-legend-item"><span className="profile-swatch" style={{ borderColor: theme === "dark" ? groupTokens[group.group] : groupColours[group.group], borderTopStyle: groupStrokes[group.group] }} aria-hidden="true" /><strong>{groupNames[group.group] || group.group}</strong><span>{number(scale === "actual" ? group.actualDayCount : group.normalizedDayCount, 0)} days</span></div>)}</div>
    {hasProfiles ? <AnalysisChart option={option} imageOption={imageOption} height={390} label={`${result.query.area} ${grouping === "dayType" ? "weekday and weekend" : "seasonal"} daily household demand profiles in ${scale === "actual" ? "kWh" : "percent of daily mean"}`} exports={exports} /> : <div className="profile-empty" role="status"><p>{scale === "normalized" && result.coverage.profileEligibleDays > 0 ? "No positive-mean complete days can be compared by shape. Select hourly energy to see zero-demand days." : "No complete 24-hour Oslo days match this range. Select a wider UTC date range to compare profiles."}</p><ExportMenu>{exports}</ExportMenu></div>}
    <p className="profile-reading">Lines show the hourly median. Shading shows the 10th–90th percentile across days, when at least five days qualify; it is not uncertainty in the mean. Hours follow Europe/Oslo.</p>
    <div className="profile-coverage"><span><strong>{number(result.coverage.profileEligibleDays, 0)}</strong> complete 24-hour days</span><span><strong>{number(result.coverage.touchedDays - result.coverage.profileEligibleDays, 0)}</strong> local dates excluded</span>{result.coverage.zeroMeanDays > 0 && <span><strong>{number(result.coverage.zeroMeanDays, 0)}</strong> zero-mean days excluded from shape only</span>}<HelpPanel label="Coverage & method">
      <p>The date picker includes both selected UTC dates. The request uses [{result.query.start}, {result.query.end}) and ends at the following UTC midnight. Hours are assigned to Europe/Oslo calendar days. Profiles use only complete days with 24 valid, selected hourly observations. Partial boundary days, 23/25-hour daylight-saving days and incomplete days are excluded from profiles; their observed hours remain in the raw-day table and CSV. Zero-mean days count in kWh profiles but not in normalized shape.</p>
      <p>{number(result.coverage.observedHours, 0)} of {number(result.coverage.expectedHours, 0)} selected UTC hours observed · {number(result.coverage.missingHours, 0)} missing · {number(result.coverage.badQualityHours, 0)} bad-quality · {number(result.coverage.nonfiniteOrNegativeHours, 0)} nonfinite/negative. {number(result.coverage.expectedDays, 0)} whole Oslo days were contained in the range; {number(result.coverage.touchedDays, 0)} were touched overall. {number(result.coverage.boundaryExcludedDays, 0)} were partial boundaries, {number(result.coverage.dstExcludedDays, 0)} DST days and {number(result.coverage.incompleteExcludedDays, 0)} incomplete. These exclusion categories may overlap. {number(result.coverage.zeroMeanDays, 0)} complete days had zero mean.</p>
      <p>Each line is the median of its group at each local hour; the band is the empirical 10th–90th percentile of observed days, not a confidence interval. It appears with five or more eligible days. Shape divides each day’s hourly kWh by that day’s positive mean, then multiplies by 100. Weekdays include public holidays; winter (DJF) pools selected December, January and February days across years. Representatives are actual observed eligible days closest to their group’s median normalized shape. Area-level aggregates do not identify household types or individual behavior.</p>
      <p>Source: {result.dataMode === "fixture" ? "synthetic fixture" : "published Elhub household consumption"}. Download Data & method JSON for calculation definitions, coverage and provenance.</p>
    </HelpPanel></div>
    <div className="profile-representatives"><h3>Representative observed days</h3><div>{groups.map((group) => <div key={group.group}><span>{groupNames[group.group] || group.group}</span>{group.representative ? <button type="button" onClick={() => inspectDate(group.representative!.date)} aria-label={`Inspect ${groupNames[group.group] || group.group} representative day ${group.representative.date}`}>{group.representative.date} <span aria-hidden="true">↗</span></button> : <span>Unavailable</span>}</div>)}</div></div>
    <details className="profile-disclosure"><summary>Hourly profile values</summary><div className="profile-table-scroll" role="region" aria-label="Hourly profile values" tabIndex={0}><table><thead><tr><th scope="col">Group</th><th scope="col">Oslo hour</th><th scope="col">Days</th><th scope="col">Median</th><th scope="col">10th</th><th scope="col">90th</th></tr></thead><tbody>{groups.flatMap((group) => (scale === "actual" ? group.actual : group.normalized).map((row) => { const point = values(row, scale); return <tr key={`${group.group}-${row.hour}`}><th scope="row">{groupNames[group.group] || group.group}</th><td>{String(row.hour).padStart(2, "0")}:00</td><td>{scale === "actual" ? group.actualDayCount : group.normalizedDayCount}</td><td>{number(point.median, 1)}</td><td>{number(point.p10, 1)}</td><td>{number(point.p90, 1)}</td></tr>; }))}</tbody></table></div><p>Values are {scale === "actual" ? "hourly kWh" : "% of each day’s mean"}. A dash means fewer than five eligible days for a percentile, or no eligible days for a median.</p></details>
    <details ref={dayDetails} className="profile-days"><summary ref={daySummary}>Observed day detail</summary><div className="profile-days-heading"><div><p>Inspect source hours, including partial and daylight-saving days.</p></div>{result.days.length > 0 && <label>Oslo date <Select aria-label="Observed Oslo date" value={selectedDay?.date || ""} onChange={(event) => setChosenDate(event.target.value)}>{result.days.map((day) => <option key={day.date} value={day.date}>{day.date}</option>)}</Select></label>}</div>
      {selectedDay ? <><p className="profile-day-status">{selectedDay.date} · {selectedDay.expectedHours} local hours · {selectedDay.validHours} valid of {selectedDay.selectedHours} selected · {selectedDay.profileEligible ? "Included in kWh profiles" : "Excluded from profiles"}{selectedDay.profileEligible && !selectedDay.normalizedEligible ? " · excluded from shape (zero mean)" : ""}</p>{selectedDay.exclusionReasons.length > 0 && <p className="profile-day-reasons">{selectedDay.exclusionReasons.map((reason) => reasons[reason] || reason).join(" · ")}</p>}
        <div className="profile-table-scroll" role="region" aria-label={`Raw hourly observations for ${selectedDay.date}`} tabIndex={0}><table><thead><tr><th scope="col">Oslo time · offset</th><th scope="col">UTC hour</th><th scope="col">Household energy (kWh)</th></tr></thead><tbody>{selectedDay.hours.map((hour) => <tr key={hour.timeUtc}><th scope="row">{localTime(hour.timeOslo)}</th><td>{hour.timeUtc.replace("T", " ").replace("Z", " UTC")}</td><td>{number(hour.valueKwh, 1)}</td></tr>)}</tbody></table></div></> : <p className="profile-empty">No observed days in this date range. Select another date range.</p>}
    </details>
  </section>;
}

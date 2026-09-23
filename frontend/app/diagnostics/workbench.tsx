"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import type { EChartsCoreOption } from "echarts/core";

import AnalysisChart from "@/components/analysis-chart";
import { AnalysisShell } from "@/components/analysis-shell";
import { AppliedFilters } from "@/components/applied-filters";
import { DateRangePicker, parseDate } from "@/components/date-range-picker";
import { HelpPanel, HelpTip } from "@/components/help";
import { Select } from "@/components/ui/select";
import { areas, getJson, number, shiftDay, type Coverage } from "@/lib/api";
import { ExportMenu } from "@/components/export-menu";
import { downloadCsv, downloadJson } from "@/lib/download";
import { writeDashboardUrl } from "@/lib/navigation-state";
import SensitivityView from "./sensitivity-view";
import DemandAnomaliesView from "./demand-anomalies-view";
import DemandChangesView from "./demand-changes-view";
import "./diagnostics.css";

type View = "correlation" | "decomposition" | "quality" | "sensitivity" | "demand_anomalies" | "demand_changes";
const viewOptions: View[] = ["correlation", "decomposition", "quality", "sensitivity", "demand_anomalies", "demand_changes"];
type Row = { time: string } & Record<string, number | boolean | null | string>;
type Metadata = {
  analyzedPoints: number;
  returnedChartPoints: number;
  chartPayloadLimited: boolean;
  interval: { start: string; end: string; bounds: string };
  provenance: unknown;
  coverage?: {
    expectedHours: number;
    pairedHours?: number;
    observedHours?: number;
    weatherRows?: number;
  };
  [key: string]: unknown;
};
type Correlation = {
  query: Record<string, unknown>;
  units: { weather: string; energy: string; correlation: string };
  summary: {
    pairedHours: number;
    correlationHours: number;
    meanCorrelation: number | null;
    latestCorrelation: number | null;
  };
  values: Row[];
  metadata: Metadata;
};
type Decomposition = {
  query: Record<string, unknown>;
  effectiveParameters: Record<string, number | boolean>;
  units: Record<string, string>;
  components: Row[];
  spectrogram: {
    times: string[];
    frequencies: number[];
    magnitude: (number | null)[][];
  };
  metadata: Metadata;
};
type Quality = {
  query: Record<string, unknown>;
  units: Record<string, string>;
  spc: {
    summary: {
      points: number;
      flags: number;
      flagPercent: number;
      robustSigma: number;
      keptCoefficients: number;
      maxAbsSatv: number;
    };
    values: Row[];
    flaggedValues: Row[];
  };
  lof: {
    summary: {
      points: number;
      flags: number;
      flagPercent: number;
      effectiveNeighbors: number;
    };
    values: Row[];
    flaggedValues: Row[];
  };
  metadata: Metadata;
};
type DiagnosticsFilters = {
  view: View;
  area: string;
  start: string;
  end: string;
  kind: "production" | "consumption";
  group: string;
  weather: string;
  windowHours: number;
  lagHours: number;
  normalize: boolean;
  period: number;
  seasonal: number;
  trend: number;
  robust: boolean;
  spectrogramWindow: number;
  spectrogramOverlap: number;
  dctFraction: number;
  k: number;
  contamination: number;
  neighbors: number;
};

const productionGroups = ["hydro", "other", "solar", "thermal", "wind"];
const consumptionGroups = [
  "cabin",
  "household",
  "primary",
  "secondary",
  "tertiary",
];
const weatherVariables = [
  "temperature_2m (°C)",
  "precipitation (mm)",
  "wind_speed_10m (m/s)",
  "wind_gusts_10m (m/s)",
  "wind_direction_10m (°)",
];
const palette = {
  green: "#176b59",
  gold: "#d18d2f",
  red: "#c55252",
  slate: "#526a60",
  pale: "rgba(23,107,89,.14)",
};

function queryValue(params: URLSearchParams, key: string, fallback: string) {
  return params.get(key) || fallback;
}

function asNumber(params: URLSearchParams, key: string, fallback: number) {
  const raw = params.get(key);
  if (raw == null || raw.trim() === "") return fallback;
  const value = Number(raw);
  return Number.isFinite(value) ? value : fallback;
}

function dashboardParams(filters: DiagnosticsFilters, candidate = "") {
  if (filters.view === "sensitivity") {
    return new URLSearchParams({ view: "sensitivity", area: filters.area });
  }
  if (filters.view === "demand_anomalies") {
    const params = new URLSearchParams({ view: "demand_anomalies", area: filters.area });
    if (candidate) params.set("candidate", candidate);
    return params;
  }
  if (filters.view === "demand_changes") {
    return new URLSearchParams({ view: "demand_changes" });
  }
  const params = new URLSearchParams({
    view: filters.view,
    area: filters.area,
    start: filters.start,
    end: filters.end,
  });
  if (filters.view !== "quality") {
    params.set("kind", filters.kind);
    params.set("group", filters.group);
  }
  if (filters.view === "correlation") {
    params.set("weather", filters.weather);
    params.set("window", String(filters.windowHours));
    params.set("lag", String(filters.lagHours));
    params.set("normalize", String(filters.normalize));
  }
  if (filters.view === "decomposition") {
    params.set("period", String(filters.period));
    params.set("seasonal", String(filters.seasonal));
    params.set("trend", String(filters.trend));
    params.set("robust", String(filters.robust));
    params.set("specWindow", String(filters.spectrogramWindow));
    params.set("overlap", String(filters.spectrogramOverlap));
  }
  if (filters.view === "quality") {
    params.set("dct", String(filters.dctFraction));
    params.set("k", String(filters.k));
    params.set("contamination", String(filters.contamination));
    params.set("neighbors", String(filters.neighbors));
  }
  return params;
}

function lineOption(
  rows: Row[],
  series: { key: string; name: string; color: string; axis?: number }[],
  units: string[],
): EChartsCoreOption {
  return {
    color: series.map((item) => item.color),
    tooltip: { trigger: "axis" },
    legend: { top: 2 },
    grid: { left: 58, right: units.length > 1 ? 58 : 20, top: 46, bottom: 62 },
    dataZoom: [{ type: "inside" }, { type: "slider", bottom: 8, height: 20 }],
    xAxis: { type: "time", axisLabel: { hideOverlap: true } },
    yAxis: units.map((unit, index) => ({
      type: "value",
      name: unit,
      position: index ? "right" : "left",
      scale: true,
    })),
    series: series.map((item) => ({
      type: "line",
      name: item.name,
      yAxisIndex: item.axis || 0,
      showSymbol: false,
      connectNulls: false,
      lineStyle: { width: 1.5 },
      data: rows.map((row) => [row.time, row[item.key]]),
    })),
  };
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}

function CoverageNote({ metadata, view }: { metadata: Metadata; view: View }) {
  const coverage = metadata.coverage;
  if (!coverage) return null;
  const observed =
    view === "correlation"
      ? coverage.pairedHours
      : view === "decomposition"
        ? coverage.observedHours
        : coverage.weatherRows;
  if (observed == null || observed >= coverage.expectedHours) return null;
  const policy =
    view === "correlation"
      ? "Correlation uses observed energy/weather pairs; missing values are not replaced with zero."
      : view === "quality"
        ? "SPC follows its documented interpolation policy; LOF never treats missing rain as dry weather."
        : "STL and the spectrogram require a complete hourly energy series.";
  return (
    <div className="diagnostics-coverage" role="status">
      <strong>Partial observed coverage</strong>
      <span>
        {observed.toLocaleString("en-GB")} of{" "}
        {coverage.expectedHours.toLocaleString("en-GB")} expected hours entered
        this analysis. {policy}
      </span>
    </div>
  );
}

function FlagTable({
  title,
  rows,
  columns,
}: {
  title: string;
  rows: Row[];
  columns: string[];
}) {
  return (
    <details>
      <summary>
        {title} ({rows.length.toLocaleString("en-GB")})
      </summary>
      <div className="diagnostics-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time (UTC)</th>
              {columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 30).map((row) => (
              <tr key={row.time}>
                <td>{row.time.replace("T", " ").slice(0, 16)}</td>
                {columns.map((column) => (
                  <td key={column}>
                    {typeof row[column] === "number"
                      ? number(row[column] as number, 3)
                      : String(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > 30 && (
        <HelpTip label="Rows shown">
          Showing the first 30 flags. The CSV download includes every returned
          flag.
        </HelpTip>
      )}
    </details>
  );
}

export default function DiagnosticsWorkbench() {
  const [view, setView] = useState<View>("correlation");
  const [area, setArea] = useState("NO1");
  const [candidate, setCandidate] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [kind, setKind] = useState<"production" | "consumption">("production");
  const [group, setGroup] = useState("hydro");
  const [weather, setWeather] = useState(weatherVariables[0]);
  const [windowHours, setWindowHours] = useState(168);
  const [lagHours, setLagHours] = useState(0);
  const [normalize, setNormalize] = useState(true);
  const [period, setPeriod] = useState(24);
  const [seasonal, setSeasonal] = useState(13);
  const [trend, setTrend] = useState(365);
  const [robust, setRobust] = useState(true);
  const [spectrogramWindow, setSpectrogramWindow] = useState(168);
  const [spectrogramOverlap, setSpectrogramOverlap] = useState(84);
  const [dctFraction, setDctFraction] = useState(0.01);
  const [k, setK] = useState(3);
  const [contamination, setContamination] = useState(0.01);
  const [neighbors, setNeighbors] = useState(60);
  const [result, setResult] = useState<
    Correlation | Decomposition | Quality | null
  >(null);
  const [applied, setApplied] = useState<DiagnosticsFilters | null>(null);
  const [pendingRestore, setPendingRestore] =
    useState<DiagnosticsFilters | null>(null);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [status, setStatus] = useState("Loading available dates…");
  const [error, setError] = useState("");
  const request = useRef(0);

  const groups = kind === "production" ? productionGroups : consumptionGroups;
  const setDraftFilters = useCallback((next: DiagnosticsFilters) => {
    setView(next.view);
    setArea(next.area);
    setStart(next.start);
    setEnd(next.end);
    setKind(next.kind);
    setGroup(next.group);
    setWeather(next.weather);
    setWindowHours(next.windowHours);
    setLagHours(next.lagHours);
    setNormalize(next.normalize);
    setPeriod(next.period);
    setSeasonal(next.seasonal);
    setTrend(next.trend);
    setRobust(next.robust);
    setSpectrogramWindow(next.spectrogramWindow);
    setSpectrogramOverlap(next.spectrogramOverlap);
    setDctFraction(next.dctFraction);
    setK(next.k);
    setContamination(next.contamination);
    setNeighbors(next.neighbors);
  }, []);

  const restore = useCallback(
    (
      params: URLSearchParams,
      fallbackDates?: { start: string; end: string },
      bounds?: { min: string; max: string },
    ) => {
      const restoredView = queryValue(params, "view", "correlation");
      const nextView = (
        viewOptions.includes(restoredView as View)
          ? restoredView
          : "correlation"
      ) as View;
      const fallbackStart = fallbackDates?.start || "";
      const fallbackEnd = fallbackDates?.end || "";
      const requestedStart = queryValue(params, "start", fallbackStart);
      const nextStart =
        !parseDate(requestedStart) ||
        (bounds && (requestedStart < bounds.min || requestedStart > bounds.max))
          ? fallbackStart
          : requestedStart;
      const requestedEnd = queryValue(params, "end", fallbackEnd);
      const nextEnd =
        !parseDate(requestedEnd) ||
        requestedEnd < nextStart ||
        (bounds && (requestedEnd < bounds.min || requestedEnd > bounds.max))
          ? fallbackEnd < nextStart
            ? nextStart
            : fallbackEnd
          : requestedEnd;
      const restoredKind =
        queryValue(params, "kind", "production") === "consumption"
          ? "consumption"
          : "production";
      const next: DiagnosticsFilters = {
        view: nextView,
        area: queryValue(params, "area", "NO1"),
        start: nextStart,
        end: nextEnd,
        kind: restoredKind,
        group: queryValue(
          params,
          "group",
          restoredKind === "production" ? "hydro" : "household",
        ),
        weather: queryValue(params, "weather", weatherVariables[0]),
        windowHours: asNumber(params, "window", 168),
        lagHours: asNumber(params, "lag", 0),
        normalize: queryValue(params, "normalize", "true") !== "false",
        period: asNumber(params, "period", 24),
        seasonal: asNumber(params, "seasonal", 13),
        trend: asNumber(params, "trend", 365),
        robust: queryValue(params, "robust", "true") !== "false",
        spectrogramWindow: asNumber(params, "specWindow", 168),
        spectrogramOverlap: asNumber(params, "overlap", 84),
        dctFraction: asNumber(params, "dct", 0.01),
        k: asNumber(params, "k", 3),
        contamination: asNumber(params, "contamination", 0.01),
        neighbors: asNumber(params, "neighbors", 60),
      };
      setDraftFilters(next);
      setCandidate(nextView === "demand_anomalies" ? params.get("candidate") || "" : "");
      setPendingRestore(next);
    },
    [setDraftFilters],
  );

  useEffect(() => {
    const current = new URLSearchParams(window.location.search);
    let knownCoverage: Coverage | null = null;
    getJson<Coverage>("/api/coverage")
      .then((value) => {
        knownCoverage = value;
        setCoverage(value);
        restore(
          current,
          {
            start: value.suggestedRange.start,
            end: shiftDay(value.suggestedRange.end, -1),
          },
          {
            min: value.coverage.start,
            max: shiftDay(value.coverage.end, -1),
          },
        );
      })
      .catch(() =>
        restore(current, { start: "2026-08-01", end: "2026-08-28" }),
      );
    const back = () => {
      const params = new URLSearchParams(window.location.search);
      if (knownCoverage) {
        restore(
          params,
          {
            start: knownCoverage.suggestedRange.start,
            end: shiftDay(knownCoverage.suggestedRange.end, -1),
          },
          {
            min: knownCoverage.coverage.start,
            max: shiftDay(knownCoverage.coverage.end, -1),
          },
        );
      } else {
        restore(params, { start: "2026-08-01", end: "2026-08-28" });
      }
    };
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, [restore]);

  const draft = useMemo<DiagnosticsFilters>(
    () => ({
      view,
      area,
      start,
      end,
      kind,
      group,
      weather,
      windowHours,
      lagHours,
      normalize,
      period,
      seasonal,
      trend,
      robust,
      spectrogramWindow,
      spectrogramOverlap,
      dctFraction,
      k,
      contamination,
      neighbors,
    }),
    [
      area,
      contamination,
      dctFraction,
      end,
      group,
      k,
      kind,
      lagHours,
      neighbors,
      normalize,
      period,
      robust,
      seasonal,
      spectrogramOverlap,
      spectrogramWindow,
      start,
      trend,
      view,
      weather,
      windowHours,
    ],
  );

  const load = useCallback(
    async (filters: DiagnosticsFilters, replaceUrl = false) => {
      if (filters.view === "sensitivity" || filters.view === "demand_anomalies" || filters.view === "demand_changes") return;
      if (!filters.start || !filters.end) return;
      if (filters.end < filters.start) {
        setError("The end date must be on or after the start date.");
        return;
      }
      const shared = dashboardParams(filters);
      writeDashboardUrl(`${window.location.pathname}?${shared}`, {
        replace: replaceUrl,
      });
      const api = new URLSearchParams({
        area: filters.area,
        start: filters.start,
        end: shiftDay(filters.end, 1),
      });
      if (filters.view !== "quality") {
        api.set("kind", filters.kind);
        api.set("group", filters.group);
      }
      if (filters.view === "correlation") {
        api.set("weather", filters.weather);
        api.set("windowHours", String(filters.windowHours));
        api.set("lagHours", String(filters.lagHours));
        api.set("normalize", String(filters.normalize));
      }
      if (filters.view === "decomposition") {
        api.set("period", String(filters.period));
        api.set("seasonalSmoother", String(filters.seasonal));
        api.set("trendSmoother", String(filters.trend));
        api.set("robust", String(filters.robust));
        api.set("spectrogramWindow", String(filters.spectrogramWindow));
        api.set("spectrogramOverlap", String(filters.spectrogramOverlap));
      }
      if (filters.view === "quality") {
        api.set("dctFraction", String(filters.dctFraction));
        api.set("k", String(filters.k));
        api.set("contamination", String(filters.contamination));
        api.set("neighbors", String(filters.neighbors));
      }
      const sequence = ++request.current;
      setStatus("Analyzing the complete hourly series…");
      setError("");
      try {
        const data = await getJson<Correlation | Decomposition | Quality>(
          `/api/diagnostics/${filters.view}?${api}`,
        );
        if (sequence === request.current) {
          setResult(data);
          setApplied(filters);
          setStatus("");
        }
      } catch (problem) {
        if (sequence === request.current) {
          setError(
            problem instanceof Error
              ? problem.message
              : "The analysis could not be loaded.",
          );
          setStatus("");
        }
      }
    },
    [],
  );

  useEffect(() => {
    if (!pendingRestore) return;
    setPendingRestore(null);
    if (pendingRestore.view === "sensitivity" || pendingRestore.view === "demand_anomalies" || pendingRestore.view === "demand_changes") return;
    void load(pendingRestore, true);
  }, [load, pendingRestore]); // Initial dates and browser history restore the complete view.

  function submit(event: FormEvent) {
    event.preventDefault();
    void load(draft);
  }
  function chooseView(next: View) {
    request.current += 1;
    setView(next);
    setCandidate("");
    setStatus("");
    setError("");
    writeDashboardUrl(
      `${window.location.pathname}?${dashboardParams({ ...draft, view: next })}`,
    );
  }
  const dirty = !applied || JSON.stringify(draft) !== JSON.stringify(applied);
  const fileStem = applied
    ? `${applied.area}-${applied.start}-${applied.end}-${applied.view}`
    : `${area}-${start}-${end}-${view}`;

  return (
    <AnalysisShell
      title="Patterns & anomalies"
      description="Relationships, seasonal patterns and changes in household demand."
    >
      <div className="analysis-picker">
        <label htmlFor="analysis-view">Analysis</label>
        <Select id="analysis-view" aria-label="Analysis" value={view} onChange={(event) => chooseView(event.target.value as View)}>
          <option value="correlation">Weather & energy</option>
          <option value="decomposition">Seasonal patterns</option>
          <option value="quality">Unusual observations</option>
          <option value="sensitivity">Demand sensitivity</option>
          <option value="demand_anomalies">Demand anomalies</option>
          <option value="demand_changes">Demand changes</option>
        </Select>
      </div>
      {view === "sensitivity" ? (
        <SensitivityView
          area={area}
          onAreaChange={(next) => {
            setArea(next);
            writeDashboardUrl(
              `${window.location.pathname}?${dashboardParams({ ...draft, view: "sensitivity", area: next })}`,
            );
          }}
        />
      ) : view === "demand_changes" ? (
        <DemandChangesView />
      ) : view === "demand_anomalies" ? (
        <DemandAnomaliesView
          area={area}
          candidate={candidate}
          onAreaChange={(next) => {
            setArea(next);
            setCandidate("");
            writeDashboardUrl(
              `${window.location.pathname}?${dashboardParams({ ...draft, view: "demand_anomalies", area: next })}`,
            );
          }}
          onCandidateChange={(next) => {
            setCandidate(next);
            writeDashboardUrl(
              `${window.location.pathname}?${dashboardParams({ ...draft, view: "demand_anomalies" }, next)}`,
            );
          }}
        />
      ) : (
      <>
      <form className="analysis-controls" onSubmit={submit}>
        <label>
          Price area
          <Select
            aria-label="Price area"
            value={area}
            onChange={(event) => setArea(event.target.value)}
          >
            {Object.entries(areas).map(([code, name]) => (
              <option key={code} value={code}>
                {code} · {name}
              </option>
            ))}
          </Select>
        </label>
        <DateRangePicker
          value={{ start, end }}
          onChange={(range) => {
            setStart(range.start);
            setEnd(range.end);
          }}
          min={coverage?.coverage.start}
          max={coverage ? shiftDay(coverage.coverage.end, -1) : undefined}
          presets={Boolean(coverage)}
        />
        {view !== "quality" && (
          <>
            <label>
              Energy kind
              <Select
                aria-label="Energy kind"
                value={kind}
                onChange={(event) => {
                  const next = event.target.value as
                    "production" | "consumption";
                  setKind(next);
                  setGroup(next === "production" ? "hydro" : "household");
                }}
              >
                <option value="production">Production</option>
                <option value="consumption">Consumption</option>
              </Select>
            </label>
            <label>
              Energy group
              <Select
                aria-label="Energy group"
                value={group}
                onChange={(event) => setGroup(event.target.value)}
              >
                {groups.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </Select>
            </label>
          </>
        )}
        <details className="filter-disclosure">
          <summary>Method settings</summary>
          <div className="method-settings-fields">
            {view === "correlation" && (
              <>
                <label>
                  Weather variable
                  <Select
                    aria-label="Weather variable"
                    value={weather}
                    onChange={(event) => setWeather(event.target.value)}
                  >
                    {weatherVariables.map((item) => (
                      <option key={item}>{item}</option>
                    ))}
                  </Select>
                </label>
                <label>
                  Window, hours
                  <input
                    type="number"
                    min={12}
                    max={720}
                    step={6}
                    value={windowHours}
                    onChange={(event) =>
                      setWindowHours(Number(event.target.value))
                    }
                  />
                </label>
                <label>
                  Lag, hours
                  <input
                    type="number"
                    min={-240}
                    max={240}
                    value={lagHours}
                    onChange={(event) =>
                      setLagHours(Number(event.target.value))
                    }
                  />
                </label>
                <label className="check-control">
                  <input
                    type="checkbox"
                    checked={normalize}
                    onChange={(event) => setNormalize(event.target.checked)}
                  />{" "}
                  Compare shapes (standardized)
                </label>
              </>
            )}
            {view === "decomposition" && (
              <>
                <label>
                  STL period, hours
                  <input
                    type="number"
                    min={2}
                    max={2000}
                    value={period}
                    onChange={(event) => setPeriod(Number(event.target.value))}
                  />
                </label>
                <label>
                  Seasonal smoother
                  <input
                    type="number"
                    min={3}
                    max={9999}
                    value={seasonal}
                    onChange={(event) =>
                      setSeasonal(Number(event.target.value))
                    }
                  />
                </label>
                <label>
                  Trend smoother
                  <input
                    type="number"
                    min={3}
                    max={9999}
                    value={trend}
                    onChange={(event) => setTrend(Number(event.target.value))}
                  />
                </label>
                <label className="check-control">
                  <input
                    type="checkbox"
                    checked={robust}
                    onChange={(event) => setRobust(event.target.checked)}
                  />{" "}
                  Robust STL
                </label>
                <label>
                  Spectral window, hours
                  <input
                    type="number"
                    min={8}
                    max={4096}
                    value={spectrogramWindow}
                    onChange={(event) =>
                      setSpectrogramWindow(Number(event.target.value))
                    }
                  />
                </label>
                <label>
                  Overlap, hours
                  <input
                    type="number"
                    min={0}
                    max={4095}
                    value={spectrogramOverlap}
                    onChange={(event) =>
                      setSpectrogramOverlap(Number(event.target.value))
                    }
                  />
                </label>
              </>
            )}
            {view === "quality" && (
              <>
                <label>
                  DCT fraction
                  <input
                    type="number"
                    min={0.001}
                    max={0.05}
                    step={0.001}
                    value={dctFraction}
                    onChange={(event) =>
                      setDctFraction(Number(event.target.value))
                    }
                  />
                </label>
                <label>
                  Band width, robust σ
                  <input
                    type="number"
                    min={1}
                    max={6}
                    step={0.1}
                    value={k}
                    onChange={(event) => setK(Number(event.target.value))}
                  />
                </label>
                <label>
                  LOF contamination
                  <input
                    type="number"
                    min={0.001}
                    max={0.05}
                    step={0.001}
                    value={contamination}
                    onChange={(event) =>
                      setContamination(Number(event.target.value))
                    }
                  />
                </label>
                <label>
                  LOF neighbors
                  <input
                    type="number"
                    min={10}
                    max={120}
                    step={5}
                    value={neighbors}
                    onChange={(event) =>
                      setNeighbors(Number(event.target.value))
                    }
                  />
                </label>
              </>
            )}
          </div>
        </details>
        <button type="submit">Run analysis</button>
      </form>
      {applied && (
        <AppliedFilters
          dirty={dirty}
          loading={Boolean(status)}
          onReset={() => {
            request.current += 1;
            setDraftFilters(applied);
            writeDashboardUrl(
              `${window.location.pathname}?${dashboardParams(applied)}`,
              { replace: true },
            );
            setStatus("");
            setError("");
          }}
        />
      )}
      {status && (
        <div className="diagnostics-state" role="status">
          {status}
        </div>
      )}
      {error && (
        <div className="diagnostics-state diagnostics-error" role="alert">
          <strong>Analysis unavailable</strong>
          <span>{error}</span>
        </div>
      )}
      {result && (
        <>
          <CoverageNote
            metadata={result.metadata}
            view={applied?.view ?? view}
          />
          <div className="analysis-actions">
            <ExportMenu label="Export metadata">
              <button
                onClick={() =>
                  downloadJson(`${fileStem}-metadata.json`, {
                    query: result.query,
                    units: result.units,
                    metadata: result.metadata,
                    ...(applied?.view === "decomposition"
                      ? {
                          effectiveParameters: (result as Decomposition)
                            .effectiveParameters,
                        }
                      : {}),
                  })
                }
              >
                Download metadata JSON
              </button>
            </ExportMenu>
            <span>
              {result.metadata.analyzedPoints.toLocaleString("en-GB")} hourly
              points analyzed
              {result.metadata.chartPayloadLimited
                ? `; chart payload reduced to ${result.metadata.returnedChartPoints.toLocaleString("en-GB")}`
                : ""}
              .
            </span>
          </div>
        </>
      )}
      {applied?.view === "correlation" && result && (
        <CorrelationView data={result as Correlation} fileStem={fileStem} />
      )}
      {applied?.view === "decomposition" && result && (
        <DecompositionView data={result as Decomposition} fileStem={fileStem} />
      )}
      {applied?.view === "quality" && result && (
        <QualityView data={result as Quality} fileStem={fileStem} />
      )}
      </>
      )}
    </AnalysisShell>
  );
}

function CorrelationView({
  data,
  fileStem,
}: {
  data: Correlation;
  fileStem: string;
}) {
  const comparison = useMemo(
    () =>
      lineOption(
        data.values,
        [
          { key: "weather", name: "Weather", color: palette.green },
          {
            key: "energy",
            name: "Energy",
            color: palette.gold,
            axis: data.units.energy === data.units.weather ? 0 : 1,
          },
        ],
        data.units.energy === data.units.weather
          ? [data.units.energy]
          : [data.units.weather, data.units.energy],
      ),
    [data],
  );
  const correlation = useMemo(
    () =>
      ({
        ...lineOption(
          data.values,
          [
            {
              key: "correlation",
              name: "Rolling Pearson r",
              color: palette.green,
            },
          ],
          ["Pearson r"],
        ),
        yAxis: { type: "value", name: "Pearson r", min: -1.05, max: 1.05 },
        series: [
          {
            type: "line",
            name: "Rolling Pearson r",
            showSymbol: false,
            connectNulls: false,
            data: data.values.map((row) => [row.time, row.correlation]),
            markLine: {
              symbol: "none",
              lineStyle: { color: "#9caaa2", type: "dashed" },
              data: [{ yAxis: 0 }],
            },
          },
        ],
      }) as EChartsCoreOption,
    [data],
  );
  return (
    <>
      <div className="analysis-metrics">
        <Metric
          label="Paired hours"
          value={data.summary.pairedHours.toLocaleString("en-GB")}
        />
        <Metric
          label="Mean rolling r"
          value={number(data.summary.meanCorrelation, 3)}
        />
        <Metric
          label="Latest rolling r"
          value={number(data.summary.latestCorrelation, 3)}
        />
      </div>
      <section className="analysis-panel">
        <h2>Aligned hourly series</h2>
        <HelpTip label="Alignment and scaling">
          Positive lag moves weather forward in time. “Compare shapes” puts both
          series on a standard-deviation scale, without physical units. It
          changes this chart only, not the correlation calculation.
        </HelpTip>
        <AnalysisChart
          option={comparison}
          label="Aligned weather and energy series"

          exports={
            <button
              onClick={() => downloadCsv(`${fileStem}-values.csv`, data.values)}
            >
              Download displayed values CSV
            </button>
          }
        />
      </section>
      <section className="analysis-panel">
        <h2>Centered rolling correlation</h2>
        <p>Correlation shows association, not causation.</p>
        <HelpTip label="Rolling window">
          Each value uses a complete centered window.
        </HelpTip>
        <AnalysisChart
          option={correlation}
          label="Sliding Pearson correlation"
        />
      </section>
      <HelpPanel label="Correlation method and provenance">
        <pre>{JSON.stringify(data.metadata, null, 2)}</pre>
      </HelpPanel>
    </>
  );
}

function DecompositionView({
  data,
  fileStem,
}: {
  data: Decomposition;
  fileStem: string;
}) {
  const observed = useMemo(
    () =>
      lineOption(
        data.components,
        [
          { key: "observed", name: "Observed", color: palette.slate },
          { key: "trend", name: "Trend", color: palette.green },
        ],
        ["kWh"],
      ),
    [data],
  );
  const remainder = useMemo(
    () =>
      lineOption(
        data.components,
        [
          { key: "seasonal", name: "Seasonal", color: palette.gold },
          { key: "resid", name: "Residual", color: palette.red },
        ],
        ["kWh"],
      ),
    [data],
  );
  const heatmap = useMemo(
    () =>
      ({
        tooltip: { position: "top" },
        grid: { left: 68, right: 25, top: 72, bottom: 70 },
        dataZoom: [
          { type: "inside", xAxisIndex: 0 },
          { type: "slider", xAxisIndex: 0, bottom: 10, height: 20 },
        ],
        xAxis: {
          type: "category",
          name: "Time (UTC)",
          data: data.spectrogram.times,
          axisLabel: {
            formatter: (value: string) => value.slice(0, 10),
            hideOverlap: true,
          },
        },
        yAxis: {
          type: "category",
          name: "cycles/day",
          data: data.spectrogram.frequencies.map((value) => number(value, 2)),
        },
        visualMap: {
          min: 0,
          max: Math.max(
            1,
            ...data.spectrogram.magnitude
              .flat()
              .filter((value): value is number => value != null),
          ),
          calculable: true,
          orient: "horizontal",
          left: "center",
          top: 8,
          inRange: { color: ["#eef4ef", "#7baa75", "#176b59", "#d18d2f"] },
        },
        series: [
          {
            type: "heatmap",
            data: data.spectrogram.magnitude.flatMap((row, y) =>
              row.map((value, x) => [x, y, value]),
            ),
            progressive: 5000,
          },
        ],
      }) as EChartsCoreOption,
    [data],
  );
  const spectralRows = data.spectrogram.frequencies.flatMap((frequency, y) =>
    data.spectrogram.times.map((time, x) => ({
      time,
      frequency_cpd: frequency,
      magnitude: data.spectrogram.magnitude[y][x],
    })),
  );
  return (
    <>
      <div className="analysis-metrics">
        <Metric
          label="Analyzed hours"
          value={data.metadata.analyzedPoints.toLocaleString("en-GB")}
        />
        <Metric
          label="STL period"
          value={`${data.effectiveParameters.period} h`}
        />
        <Metric
          label="Effective smoothers"
          value={`${data.effectiveParameters.seasonalSmoother} / ${data.effectiveParameters.trendSmoother}`}
          detail="seasonal / trend"
        />
      </div>
      <section className="analysis-panel">
        <h2>Observed and trend</h2>
        <AnalysisChart
          option={observed}
          label="STL observed energy and trend"

          exports={
            <>
              <button
                onClick={() =>
                  downloadCsv(`${fileStem}-components.csv`, data.components)
                }
              >
                Download components CSV
              </button>
            </>
          }
        />
      </section>
      <section className="analysis-panel">
        <h2>Seasonal pattern and residual</h2>
        <AnalysisChart
          option={remainder}
          label="STL seasonal and residual components"
        />
      </section>
      <section className="analysis-panel">
        <h2>Frequency through time</h2>
        <HelpTip label="Reading the spectrum">
          Brighter regions show stronger repeating behavior. Frequencies are
          shown from 0 to 12 cycles per day.
        </HelpTip>
        <AnalysisChart
          option={heatmap}
          label="Energy spectrogram"
          height={440}

          exports={
            <button
              onClick={() =>
                downloadCsv(`${fileStem}-spectrogram.csv`, spectralRows)
              }
            >
              Download spectral values CSV
            </button>
          }
        />
      </section>
      <HelpPanel label="Decomposition parameters and provenance">
        <pre>
          {JSON.stringify(
            {
              effectiveParameters: data.effectiveParameters,
              metadata: data.metadata,
            },
            null,
            2,
          )}
        </pre>
      </HelpPanel>
    </>
  );
}

function QualityView({ data, fileStem }: { data: Quality; fileStem: string }) {
  const spc = useMemo(
    () =>
      ({
        ...lineOption(
          data.spc.values,
          [
            { key: "lo", name: "Lower band", color: "#a2aea5" },
            { key: "hi", name: "Upper band", color: "#a2aea5" },
            { key: "trend", name: "DCT trend", color: palette.green },
            { key: "value", name: "Temperature", color: palette.slate },
          ],
          ["°C"],
        ),
        legend: { type: "scroll", top: 2 },
        grid: { left: 62, right: 20, top: 62, bottom: 62 },
        yAxis: {
          type: "value",
          name: "°C",
          nameLocation: "middle",
          nameGap: 42,
          scale: true,
        },
        series: [
          {
            type: "line",
            name: "Lower band",
            showSymbol: false,
            data: data.spc.values.map((row) => [row.time, row.lo]),
            lineStyle: { opacity: 0.65 },
          },
          {
            type: "line",
            name: "Upper band",
            showSymbol: false,
            data: data.spc.values.map((row) => [row.time, row.hi]),
            areaStyle: { color: palette.pale, origin: "start" },
            lineStyle: { opacity: 0.65 },
          },
          {
            type: "line",
            name: "DCT trend",
            showSymbol: false,
            data: data.spc.values.map((row) => [row.time, row.trend]),
            lineStyle: { color: palette.green, type: "dashed" },
          },
          {
            type: "line",
            name: "Temperature",
            showSymbol: false,
            data: data.spc.values.map((row) => [row.time, row.value]),
            lineStyle: { color: palette.slate },
          },
          {
            type: "scatter",
            name: "Flags",
            data: data.spc.flaggedValues.map((row) => [row.time, row.value]),
            itemStyle: { color: palette.red },
            symbolSize: 7,
          },
        ],
      }) as EChartsCoreOption,
    [data],
  );
  const lof = useMemo(
    () =>
      ({
        ...lineOption(
          data.lof.values,
          [{ key: "precip", name: "Precipitation", color: palette.green }],
          ["mm"],
        ),
        series: [
          {
            type: "line",
            name: "Precipitation",
            showSymbol: false,
            data: data.lof.values.map((row) => [row.time, row.precip]),
            lineStyle: { color: palette.green },
          },
          {
            type: "scatter",
            name: "Flags",
            data: data.lof.flaggedValues.map((row) => [row.time, row.precip]),
            itemStyle: { color: palette.red },
            symbolSize: 7,
          },
        ],
      }) as EChartsCoreOption,
    [data],
  );
  return (
    <>
      <div className="diagnostics-notice">
        <strong>Inspection candidates</strong>
        <span>
          These flags are statistical signals. Cold snaps, storms, and heavy
          rain can be real observations; a flag is not a verified data fault.
        </span>
      </div>
      <div className="analysis-grid">
        <section className="analysis-panel">
          <h2>Temperature control band</h2>
          <div className="analysis-metrics">
            <Metric
              label="SPC flags"
              value={data.spc.summary.flags.toLocaleString("en-GB")}
              detail={`${number(data.spc.summary.flagPercent, 2)}% of points`}
            />
            <Metric
              label="Robust σ"
              value={number(data.spc.summary.robustSigma, 3)}
            />
            <Metric
              label="Max |SATV|"
              value={number(data.spc.summary.maxAbsSatv, 2)}
            />
          </div>
          <AnalysisChart
            option={spc}
            label="Temperature SPC control band and flags"

            exports={
              <>
                <button
                  onClick={() =>
                    downloadCsv(`${fileStem}-spc-values.csv`, data.spc.values)
                  }
                >
                  Download displayed SPC values
                </button>
                <button
                  onClick={() =>
                    downloadCsv(
                      `${fileStem}-spc-flags.csv`,
                      data.spc.flaggedValues,
                    )
                  }
                >
                  Download SPC flags
                </button>
              </>
            }
          />
          <FlagTable
            title="SPC flag table"
            rows={data.spc.flaggedValues}
            columns={["value", "trend", "satv"]}
          />
        </section>
        <section className="analysis-panel">
          <h2>Precipitation anomalies</h2>
          <div className="analysis-metrics">
            <Metric
              label="LOF flags"
              value={data.lof.summary.flags.toLocaleString("en-GB")}
              detail={`${number(data.lof.summary.flagPercent, 2)}% of points`}
            />
            <Metric
              label="Neighbors used"
              value={String(data.lof.summary.effectiveNeighbors)}
            />
            <Metric
              label="Analyzed points"
              value={data.lof.summary.points.toLocaleString("en-GB")}
            />
          </div>
          <AnalysisChart
            option={lof}
            label="Precipitation LOF anomalies"
            exports={
              <>
                <button
                  onClick={() =>
                    downloadCsv(`${fileStem}-lof-values.csv`, data.lof.values)
                  }
                >
                  Download displayed LOF values
                </button>
                <button
                  onClick={() =>
                    downloadCsv(
                      `${fileStem}-lof-flags.csv`,
                      data.lof.flaggedValues,
                    )
                  }
                >
                  Download LOF flags
                </button>
              </>
            }
          />
          <FlagTable
            title="LOF flag table"
            rows={data.lof.flaggedValues}
            columns={["precip", "roll24", "lof_score"]}
          />
        </section>
      </div>
      <HelpPanel label="Anomaly methods and provenance">
        <pre>{JSON.stringify(data.metadata, null, 2)}</pre>
      </HelpPanel>
    </>
  );
}

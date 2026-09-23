"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { Download, RefreshCw } from "lucide-react";
import AnalysisChart from "@/components/analysis-chart";
import { AnalysisShell } from "@/components/analysis-shell";
import { AppliedFilters } from "@/components/applied-filters";
import { displayJson } from "@/lib/number-format";
import { DateRangePicker, parseDate } from "@/components/date-range-picker";
import { HelpPanel, HelpTip } from "@/components/help";
import { Select } from "@/components/ui/select";
import { downloadCsv, downloadJson } from "@/lib/download";
import { areas, getJson, number, shiftDay, type Coverage } from "@/lib/api";
import { writeDashboardUrl } from "@/lib/navigation-state";
import { ExplorePeaksView, type AreaPeaks } from "@/components/demand-peaks";
import { DemandProfilesView, type DemandProfilesResponse } from "@/components/demand-profiles";

type View = "energy" | "weather" | "peaks" | "profiles";
type Aggregation = "hourly" | "daily" | "weekly";
type Kind = "production" | "consumption";
type Filters = {
  view: View;
  area: string;
  start: string;
  end: string;
  kind: Kind;
  groups: string[];
  aggregation: Aggregation;
  variables: string[];
  normalize: boolean;
  rolling: number;
  opacity: number;
};
type EnergyRow = { time: string; group: string; valueKwh: number | null };
type EnergyResponse = {
  query: Omit<
    Filters,
    "view" | "variables" | "normalize" | "rolling" | "opacity" | "end"
  > & { end: string };
  unit: "kWh";
  aggregationLabel: string;
  availableGroups: string[];
  grandTotalKwh: number | null;
  totals: {
    group: string;
    totalKwh: number | null;
    observations: number;
    observedHours: number;
    expectedHours: number;
    partial: boolean;
  }[];
  series: EnergyRow[];
  coverage: {
    firstObservation: string | null;
    lastObservation: string | null;
    observations: number;
    expectedHoursPerGroup: number;
    complete: boolean;
  };
  metadata: Record<string, unknown>;
};
type WeatherRow = { time: string; variable: string; value: number | null };
type WeatherResponse = {
  query: {
    area: string;
    start: string;
    end: string;
    variables: string[];
    aggregation: Aggregation;
    rollingHours: number;
    normalize: boolean;
  };
  valueLabel: string;
  aggregationLabel: string;
  summary: {
    variable: string;
    label: string;
    unit: string;
    min: number | null;
    mean: number | null;
    max: number | null;
    observations: number;
  }[];
  monthly: ({ month: number } & Record<string, number | null>)[];
  windRose: { sector: string; count: number; share: number | null }[];
  series: WeatherRow[];
  coverage: {
    firstObservation: string | null;
    lastObservation: string | null;
    observations: number;
    expectedHours: number;
    observedHours: number;
    complete: boolean;
  };
  variableDefinitions: {
    variable: string;
    column: string;
    label: string;
    unit: string;
    aggregation: string;
  }[];
  metadata: Record<string, unknown>;
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
  ["temperature", "Temperature"],
  ["precipitation", "Precipitation"],
  ["wind_speed", "Wind speed"],
  ["wind_gusts", "Wind gusts"],
  ["wind_direction", "Wind direction"],
] as const;
const colours = ["#176b59", "#d2a83f", "#557c9a", "#9a6558", "#7775a5"];
const months = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];
const chartPointBudget = 8000;

function oneYearDefault(coverage: Coverage) {
  if (
    coverage.coverage.start <= "2025-01-01" &&
    coverage.coverage.end >= "2026-01-01"
  ) {
    return { start: "2025-01-01", end: "2025-12-31" };
  }
  const last = shiftDay(coverage.coverage.end, -1);
  const date = new Date(`${coverage.coverage.end}T00:00:00Z`);
  date.setUTCFullYear(date.getUTCFullYear() - 1);
  const candidate = date.toISOString().slice(0, 10);
  return {
    start:
      candidate < coverage.coverage.start ? coverage.coverage.start : candidate,
    end: last,
  };
}

function readFilters(coverage: Coverage): Filters {
  const params = new URLSearchParams(window.location.search);
  const fallback = oneYearDefault(coverage);
  const view = params.get("view") === "weather" ? "weather" : params.get("view") === "peaks" ? "peaks" : params.get("view") === "profiles" ? "profiles" : "energy";
  const area = Object.hasOwn(areas, params.get("area") || "")
    ? params.get("area")!
    : coverage.areas[0];
  const kind: Kind =
    params.get("kind") === "consumption" ? "consumption" : "production";
  const validGroups =
    kind === "production" ? productionGroups : consumptionGroups;
  const groups = (params.get("groups")?.split(",") || validGroups).filter(
    (value) => validGroups.includes(value),
  );
  const variables = (
    params.get("variables")?.split(",") || weatherVariables.map(([key]) => key)
  ).filter((value) => weatherVariables.some(([key]) => key === value));
  const aggregation = (
    ["hourly", "daily", "weekly"].includes(params.get("aggregation") || "")
      ? params.get("aggregation")
      : "daily"
  ) as Aggregation;
  const rolling = Math.max(
    0,
    Math.min(240, Number(params.get("rolling") ?? 24) || 0),
  );
  const opacity = Math.max(
    0.1,
    Math.min(1, Number(params.get("opacity") ?? 0.9) || 0.9),
  );
  const normalize = params.get("normalize") !== "false";
  const startParam = params.get("start") || fallback.start;
  const endParam = params.get("end") || fallback.end;
  const start =
    !parseDate(startParam) ||
    startParam < coverage.coverage.start ||
    startParam >= coverage.coverage.end
      ? fallback.start
      : startParam;
  const lastAvailable = shiftDay(coverage.coverage.end, -1);
  const end =
    !parseDate(endParam) || endParam < start || endParam > lastAvailable
      ? fallback.end < start
        ? start
        : fallback.end
      : endParam;
  return {
    view,
    area,
    start,
    end,
    kind,
    groups: groups.length ? groups : validGroups,
    aggregation,
    variables: variables.length ? variables : ["temperature"],
    normalize,
    rolling,
    opacity,
  };
}

function writeFilters(filters: Filters, replace = false) {
  const params = new URLSearchParams();
  params.set("view", filters.view);
  params.set("area", filters.area);
  params.set("start", filters.start);
  params.set("end", filters.end);
  params.set("kind", filters.kind);
  params.set("groups", filters.groups.join(","));
  params.set("aggregation", filters.aggregation);
  params.set("variables", filters.variables.join(","));
  params.set("normalize", String(filters.normalize));
  params.set("rolling", String(filters.rolling));
  params.set("opacity", String(filters.opacity));
  writeDashboardUrl(`${window.location.pathname}?${params}`, { replace });
}

function capRows<T extends { time: string }>(rows: T[], seriesCount: number) {
  const times = [...new Set(rows.map((row) => row.time))].sort();
  const maximumTimes = Math.max(
    2,
    Math.floor(chartPointBudget / Math.max(1, seriesCount)),
  );
  const stride = Math.max(1, Math.ceil(times.length / maximumTimes));
  if (stride === 1) return { rows, stride, sourcePoints: rows.length };
  const kept = new Set(
    times.filter(
      (_, index) => index % stride === 0 || index === times.length - 1,
    ),
  );
  return {
    rows: rows.filter((row) => kept.has(row.time)),
    stride,
    sourcePoints: rows.length,
  };
}

function formatUtc(value: string | null) {
  return value
    ? value
        .replace("T", " ")
        .replace(/\.000Z$/, " UTC")
        .replace("Z", " UTC")
    : "No observations";
}

function baseChart(yName: string): EChartsCoreOption {
  return {
    animation: false,
    color: colours,
    grid: { left: 72, right: 22, top: 62, bottom: 66 },
    legend: { top: 5, type: "scroll" },
    tooltip: { trigger: "axis" },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 20, bottom: 10 }],
    xAxis: {
      type: "time",
      name: "UTC",
      nameLocation: "middle",
      nameGap: 30,
      axisLabel: { color: "#607069" },
    },
    yAxis: {
      type: "value",
      name: yName,
      nameLocation: "middle",
      nameGap: 54,
      nameTextStyle: { color: "#607069" },
      axisLabel: { color: "#607069" },
      splitLine: { lineStyle: { color: "#e2e8e2" } },
    },
  };
}

export default function ExploreClient() {
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [draft, setDraft] = useState<Filters | null>(null);
  const [active, setActive] = useState<Filters | null>(null);
  const [energy, setEnergy] = useState<EnergyResponse | null>(null);
  const [weather, setWeather] = useState<WeatherResponse | null>(null);
  const [peaks, setPeaks] = useState<AreaPeaks | null>(null);
  const [profiles, setProfiles] = useState<DemandProfilesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [coverageRetry, setCoverageRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    getJson<Coverage>("/api/coverage", controller.signal)
      .then((value) => {
        const initial = readFilters(value);
        setCoverage(value);
        setDraft(initial);
        setActive(initial);
        writeFilters(initial, true);
      })
      .catch((reason) => {
        if (reason.name !== "AbortError") setError(reason.message);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [coverageRetry]);

  useEffect(() => {
    if (!coverage) return;
    const restore = () => {
      const restored = readFilters(coverage);
      setDraft(restored);
      setActive(restored);
      setError("");
    };
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, [coverage]);

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    const params = new URLSearchParams({ area: active.area, start: active.start, end: shiftDay(active.end, 1) });
    if (active.view === "energy") {
      params.set("aggregation", active.aggregation);
      params.set("kind", active.kind);
      params.set("groups", active.groups.join(","));
    } else if (active.view === "weather") {
      params.set("aggregation", active.aggregation);
      params.set("variables", active.variables.join(","));
      params.set("normalize", String(active.normalize));
      params.set("rolling_hours", String(active.rolling));
    }
    setLoading(true);
    setError("");
    setEnergy(null);
    setWeather(null);
    setPeaks(null);
    setProfiles(null);
    getJson<EnergyResponse | WeatherResponse | AreaPeaks | DemandProfilesResponse>(
      `/api/explore/${active.view === "peaks" ? "demand-peaks" : active.view === "profiles" ? "demand-profiles" : active.view}?${params}`,
      controller.signal,
    )
      .then((value) => {
        if (controller.signal.aborted) return;
        if (active.view === "energy") setEnergy(value as EnergyResponse);
        else if (active.view === "weather") setWeather(value as WeatherResponse);
        else if (active.view === "peaks") setPeaks(value as AreaPeaks);
        else setProfiles(value as DemandProfilesResponse);
      })
      .catch((reason) => {
        if (reason.name !== "AbortError") setError(reason.message);
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [active, retry]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft || draft.end < draft.start) {
      setError("The end date must be on or after the start date.");
      return;
    }
    if ((draft.view === "peaks" || draft.view === "profiles") && (Date.parse(`${shiftDay(draft.end, 1)}T00:00:00Z`) - Date.parse(`${draft.start}T00:00:00Z`)) / 86400000 > 366) {
      setError(`${draft.view === "peaks" ? "Peak" : "Daily profile"} analysis supports up to 366 inclusive dates. Choose a shorter range.`);
      return;
    }
    if (draft.view === "energy" && !draft.groups.length) {
      setError("Select at least one energy group.");
      return;
    }
    if (draft.view === "weather" && !draft.variables.length) {
      setError("Select at least one weather variable.");
      return;
    }
    writeFilters(draft);
    setActive({ ...draft });
  }

  function update(next: Partial<Filters>) {
    setDraft((current) => (current ? { ...current, ...next } : current));
  }

  const energyCap = useMemo(
    () => (energy ? capRows(energy.series, energy.query.groups.length) : null),
    [energy],
  );
  const weatherCap = useMemo(
    () =>
      weather ? capRows(weather.series, weather.query.variables.length) : null,
    [weather],
  );
  const dirty = Boolean(
    draft && active && JSON.stringify(draft) !== JSON.stringify(active),
  );

  const energyOption = useMemo<EChartsCoreOption>(() => {
    if (!energy || !energyCap) return {};
    return {
      ...baseChart("Energy (kWh)"),
      series: energy.query.groups.map((group, index) => ({
        name: group,
        type: "line",
        showSymbol: false,
        connectNulls: false,
        lineStyle: { width: 1.7, opacity: active?.opacity ?? 0.9 },
        itemStyle: { color: colours[index % colours.length] },
        data: energyCap.rows
          .filter((row) => row.group === group)
          .map((row) => [row.time, row.valueKwh]),
      })),
    };
  }, [active?.opacity, energy, energyCap]);

  const totalsOption = useMemo<EChartsCoreOption>(
    () =>
      energy
        ? {
            color: colours,
            tooltip: { trigger: "item" },
            legend: { orient: "vertical", right: 5, top: "middle" },
            series: [
              {
                type: "pie",
                radius: ["45%", "72%"],
                center: ["38%", "50%"],
                data: energy.totals
                  .filter((row) => row.totalKwh != null)
                  .map((row) => ({ name: row.group, value: row.totalKwh })),
              },
            ],
          }
        : {},
    [energy],
  );

  const weatherOption = useMemo<EChartsCoreOption>(() => {
    if (!weather || !weatherCap) return {};
    return {
      ...baseChart(weather.valueLabel),
      series: weather.query.variables.map((variable, index) => ({
        name:
          weather.variableDefinitions.find((item) => item.variable === variable)
            ?.label || variable,
        type: "line",
        showSymbol: false,
        connectNulls: false,
        lineStyle: { width: 1.7, opacity: active?.opacity ?? 0.9 },
        itemStyle: { color: colours[index % colours.length] },
        data: weatherCap.rows
          .filter((row) => row.variable === variable)
          .map((row) => [row.time, row.value]),
      })),
    };
  }, [active?.opacity, weather, weatherCap]);

  const windOption = useMemo<EChartsCoreOption>(
    () =>
      weather
        ? {
            color: ["#176b59"],
            tooltip: { trigger: "item", formatter: "{b}: {c} observations" },
            polar: { radius: [20, "70%"] },
            angleAxis: {
              type: "category",
              data: weather.windRose.map((row) => row.sector),
              startAngle: 90,
              clockwise: true,
              axisLabel: { interval: 1, color: "#607069" },
            },
            radiusAxis: {
              name: "Observed hours",
              axisLabel: { color: "#607069" },
              splitLine: { lineStyle: { color: "#e2e8e2" } },
            },
            series: [
              {
                type: "bar",
                coordinateSystem: "polar",
                data: weather.windRose.map((row) => row.count),
                barWidth: "88%",
              },
            ],
          }
        : {},
    [weather],
  );

  return (
    <AnalysisShell
      title="Explore"
    >
      {coverage && draft ? (
        <form className="analysis-controls explore-controls" onSubmit={submit}>
          <label>
            View
            <Select
              aria-label="View"
              value={draft.view}
              onChange={(event) => update({ view: event.target.value as View })}
            >
              <option value="energy">Energy</option>
              <option value="weather">Weather</option>
              <option value="peaks">Demand peaks</option>
              <option value="profiles">Daily profiles</option>
            </Select>
          </label>
          <label>
            Price area
            <Select
              aria-label="Price area"
              value={draft.area}
              onChange={(event) => update({ area: event.target.value })}
            >
              {coverage.areas.map((area) => (
                <option value={area} key={area}>
                  {area} · {areas[area]}
                </option>
              ))}
            </Select>
          </label>
          <DateRangePicker
            value={{ start: draft.start, end: draft.end }}
            onChange={(range) => update(range)}
            min={coverage.coverage.start}
            max={shiftDay(coverage.coverage.end, -1)}
            presets
          />
          {draft.view !== "peaks" && draft.view !== "profiles" && (
            <details className="filter-disclosure">
              <summary>More filters · {draft.view === "energy" ? `${draft.kind}, ${draft.groups.length} groups` : `${draft.variables.length} variables`}</summary>
              <div className="explore-filter-body">
          <label>
            Time detail
            <Select
              aria-label="Time detail"
              value={draft.aggregation}
              onChange={(event) =>
                update({ aggregation: event.target.value as Aggregation })
              }
            >
              <option value="hourly">Hourly</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
            </Select>
          </label>
          {draft.view === "energy" ? (
            <>
              <label>
                Energy kind
                <Select
                  aria-label="Energy kind"
                  value={draft.kind}
                  onChange={(event) => {
                    const kind = event.target.value as Kind;
                    update({
                      kind,
                      groups:
                        kind === "production"
                          ? productionGroups
                          : consumptionGroups,
                    });
                  }}
                >
                  <option value="production">Production</option>
                  <option value="consumption">Consumption</option>
                </Select>
              </label>
              <fieldset className="explore-options">
                <legend>Groups</legend>
                {(draft.kind === "production"
                  ? productionGroups
                  : consumptionGroups
                ).map((group) => (
                  <label key={group}>
                    <input
                      type="checkbox"
                      checked={draft.groups.includes(group)}
                      onChange={(event) =>
                        update({
                          groups: event.target.checked
                            ? [...draft.groups, group]
                            : draft.groups.filter((value) => value !== group),
                        })
                      }
                    />
                    {group}
                  </label>
                ))}
              </fieldset>
            </>
          ) : draft.view === "weather" ? (
            <>
              <fieldset className="explore-options">
                <legend>Variables</legend>
                {weatherVariables.map(([key, label]) => (
                  <label key={key}>
                    <input
                      type="checkbox"
                      checked={draft.variables.includes(key)}
                      onChange={(event) =>
                        update({
                          variables: event.target.checked
                            ? [...draft.variables, key]
                            : draft.variables.filter((value) => value !== key),
                        })
                      }
                    />
                    {label}
                  </label>
                ))}
              </fieldset>
              <label className="explore-check">
                <input
                  type="checkbox"
                  checked={draft.normalize}
                  onChange={(event) =>
                    update({ normalize: event.target.checked })
                  }
                />
                Compare shapes (scale 0–1)
              </label>
              <label>
                Smooth over · hours
                <input
                  type="number"
                  min={0}
                  max={240}
                  value={draft.rolling}
                  onChange={(event) =>
                    update({ rolling: Number(event.target.value) })
                  }
                />
              </label>
            </>
          ) : null}
          <details className="filter-disclosure display-settings">
            <summary>Display options</summary>
            <label>
              Line opacity <span>{draft.opacity.toFixed(2)}</span>
              <input
                type="range"
                min={0.1}
                max={1}
                step={0.05}
                value={draft.opacity}
                onChange={(event) =>
                  update({ opacity: Number(event.target.value) })
                }
              />
            </label>
          </details>
                <p className="explore-coverage">Available energy dates: {coverage.coverage.start}–{shiftDay(coverage.coverage.end, -1)}, inclusive UTC.</p>
              </div>
            </details>
          )}
          <button type="submit">Apply view</button>

        </form>
      ) : null}

      {active ? (
        <AppliedFilters
          dirty={dirty}
          loading={loading}
          onReset={() => {
            setDraft({ ...active });
            setError("");
          }}
        />
      ) : null}

      {loading ? (
        <section className="analysis-panel explore-state" aria-live="polite">
          <RefreshCw className="explore-spin" size={20} /> Loading published
          observations…
        </section>
      ) : null}
      {error ? (
        <section
          className="analysis-panel explore-state explore-error"
          role="alert"
        >
          <p>{error}</p>
          <button
            type="button"
            onClick={() =>
              coverage
                ? setRetry((value) => value + 1)
                : setCoverageRetry((value) => value + 1)
            }
          >
            Try again
          </button>
        </section>
      ) : null}
      {!loading && !error && energy ? (
        <EnergyView
          response={energy}
          option={energyOption}
          totalsOption={totalsOption}
          cap={energyCap!}
        />
      ) : null}
      {!loading && !error && weather ? (
        <WeatherView
          response={weather}
          option={weatherOption}
          windOption={windOption}
          cap={weatherCap!}
        />
      ) : null}
      {!loading && !error && peaks ? <ExplorePeaksView result={peaks} /> : null}
      {!loading && !error && profiles ? <DemandProfilesView result={profiles} /> : null}
    </AnalysisShell>
  );
}

function CapNote({
  stride,
  sourcePoints,
  renderedPoints,
}: {
  stride: number;
  sourcePoints: number;
  renderedPoints: number;
}) {
  return stride > 1 ? (
    <div className="explore-note">
      <HelpTip label="Chart sampling">
        The chart renders {number(renderedPoints, 0)} of{" "}
        {number(sourcePoints, 0)} exact aggregated points: every {stride}th UTC
        interval plus the final interval. Calculations and downloads use every
        point.
      </HelpTip>
    </div>
  ) : null;
}

function EnergyView({
  response,
  option,
  totalsOption,
  cap,
}: {
  response: EnergyResponse;
  option: EChartsCoreOption;
  totalsOption: EChartsCoreOption;
  cap: ReturnType<typeof capRows<EnergyRow>>;
}) {
  if (!response.series.length)
    return (
      <section className="analysis-panel explore-state">
        <p>No energy observations match this selection.</p>
      </section>
    );
  const filename = `${response.query.area}-${response.query.kind}-${response.query.start}-${shiftDay(response.query.end, -1)}`;
  return (
    <>
      <div className="analysis-metrics">
        <div>
          <span>Selected total</span>
          <strong>{number(response.grandTotalKwh, 0)} kWh</strong>
        </div>
        <div>
          <span>Coverage</span>
          <strong>{response.coverage.complete ? "Complete" : "Partial"}</strong>
          <small>
            {formatUtc(response.coverage.firstObservation)} →{" "}
            {formatUtc(response.coverage.lastObservation)}
          </small>
        </div>
        <div>
          <span>Time interval</span>
          <strong>{response.aggregationLabel}</strong>
        </div>
      </div>
      <section className="analysis-panel">
        <div className="explore-panel-heading">
          <div>
            <h2>
              {response.query.kind === "production"
                ? "Production"
                : "Consumption"}{" "}
              through time
            </h2>
          </div>
        </div>
        <AnalysisChart
          option={option}
          exports={
            <>
              <button
                type="button"
                onClick={() => downloadCsv(`${filename}.csv`, response.series)}
              >
                <Download size={14} /> Data CSV
              </button>
              <button
                type="button"
                onClick={() =>
                  downloadJson(`${filename}-metadata.json`, {
                    query: response.query,
                    coverage: response.coverage,
                    metadata: response.metadata,
                  })
                }
              >
                Metadata JSON
              </button>
            </>
          }
          label={`${response.query.kind} groups through time`}
          height={410}
        />
        <CapNote
          stride={cap.stride}
          sourcePoints={cap.sourcePoints}
          renderedPoints={cap.rows.length}
        />
      </section>
      <details className="explore-breakdown">
        <summary>Group totals and coverage</summary>
        <div className="analysis-grid">
        <div className="analysis-panel">
          <div className="analysis-title"><h2>Group totals</h2>
          <HelpTip label="How totals are calculated" iconOnly>
            Totals include every finite selected observation before chart
            sampling.
          </HelpTip></div>
          <AnalysisChart
            option={totalsOption}
            label={`${response.query.kind} group totals`}
            height={300}
          />
        </div>
        <div className="analysis-panel">
          <h2>Values behind the mix</h2>
          <div className="explore-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Group</th>
                  <th>Total kWh</th>
                  <th>Hours</th>
                  <th>Coverage</th>
                </tr>
              </thead>
              <tbody>
                {response.totals.map((row) => (
                  <tr key={row.group}>
                    <th>{row.group}</th>
                    <td>{number(row.totalKwh, 1)}</td>
                    <td>
                      {number(row.observedHours, 0)} /{" "}
                      {number(row.expectedHours, 0)}
                    </td>
                    <td>{row.partial ? "Partial" : "Complete"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        </div>
      </details>
      <HelpPanel label="Energy method and provenance">
        <pre>{displayJson(response.metadata)}</pre>
      </HelpPanel>
    </>
  );
}

function monthlyOption(
  response: WeatherResponse,
  variable: string,
): EChartsCoreOption {
  const definition = response.variableDefinitions.find(
    (item) => item.variable === variable,
  );
  return {
    color: ["#176b59"],
    grid: { left: 55, right: 14, top: 12, bottom: 36 },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: months, axisLabel: { color: "#607069" } },
    yAxis: {
      type: "value",
      name: definition?.unit,
      axisLabel: { color: "#607069" },
      splitLine: { lineStyle: { color: "#e2e8e2" } },
    },
    series: [
      {
        type: "bar",
        data: response.monthly.map((row) => row[variable]),
        itemStyle: { borderRadius: [3, 3, 0, 0] },
      },
    ],
  };
}

function WeatherView({
  response,
  option,
  windOption,
  cap,
}: {
  response: WeatherResponse;
  option: EChartsCoreOption;
  windOption: EChartsCoreOption;
  cap: ReturnType<typeof capRows<WeatherRow>>;
}) {
  if (!response.series.length)
    return (
      <section className="analysis-panel explore-state">
        <p>No weather observations match this selection.</p>
      </section>
    );
  const filename = `${response.query.area}-weather-${response.query.start}-${shiftDay(response.query.end, -1)}`;
  return (
    <>
      <div className="analysis-metrics">
        <div>
          <span>Coverage</span>
          <strong>{response.coverage.complete ? "Complete" : "Partial"}</strong>
          <small>
            {number(response.coverage.observedHours, 0)} /{" "}
            {number(response.coverage.expectedHours, 0)} hours
          </small>
        </div>
        <div>
          <span>Time interval</span>
          <strong>{response.aggregationLabel}</strong>
          {response.query.rollingHours > 0 && <small>{response.query.rollingHours} h rolling window</small>}
        </div>
        <div>
          <span>Location model</span>
          <strong>{response.query.area} city proxy</strong>
          <small>ERA5-Seamless · UTC</small>
        </div>
      </div>
      <section className="analysis-panel">
        <div className="explore-panel-heading">
          <div>
            <div className="analysis-title"><h2>Weather through time</h2>
            <HelpTip label="Weather values" iconOnly>
              {response.valueLabel}. Wind direction uses circular averages.
            </HelpTip></div>
          </div>
        </div>
        <AnalysisChart
          option={option}
          exports={
            <>
              <button
                type="button"
                onClick={() => downloadCsv(`${filename}.csv`, response.series)}
              >
                <Download size={14} /> Data CSV
              </button>
              <button
                type="button"
                onClick={() =>
                  downloadJson(`${filename}-metadata.json`, {
                    query: response.query,
                    coverage: response.coverage,
                    variables: response.variableDefinitions,
                    metadata: response.metadata,
                  })
                }
              >
                Metadata JSON
              </button>
            </>
          }
          label="Selected weather variables through time"
          height={410}
        />
        <CapNote
          stride={cap.stride}
          sourcePoints={cap.sourcePoints}
          renderedPoints={cap.rows.length}
        />
      </section>
      <details className="explore-breakdown">
        <summary>Weather breakdown</summary>
      <section className="analysis-panel">
        <h2>Selected dates</h2>
        <HelpTip label="Summary and scaling">
          Summary values retain their original units. “Compare shapes” scales
          each chart series from 0 to 1, so its axis no longer shows physical
          quantities.
        </HelpTip>
        <div className="explore-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Variable</th>
                <th>Minimum</th>
                <th>Mean</th>
                <th>Maximum</th>
                <th>Observations</th>
              </tr>
            </thead>
            <tbody>
              {response.summary.map((row) => (
                <tr key={row.variable}>
                  <th>
                    {row.label} ({row.unit})
                  </th>
                  <td>{number(row.min, 2)}</td>
                  <td>{number(row.mean, 2)}</td>
                  <td>{number(row.max, 2)}</td>
                  <td>{number(row.observations, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section>
        <div className="explore-section-heading">
          <h2>Monthly patterns</h2>
          <HelpTip label="Monthly aggregation">
            Precipitation is summed; temperature, wind speed and gusts are
            arithmetic means. Missing months remain blank.
          </HelpTip>
        </div>
        <div className="analysis-grid">
          {(
            [
              "temperature",
              "precipitation",
              "wind_speed",
              "wind_gusts",
            ] as const
          ).map((variable) => {
            const definition = response.variableDefinitions.find(
              (item) => item.variable === variable,
            );
            return (
              <div className="analysis-panel" key={variable}>
                <h3>{definition?.label}</h3>
                <AnalysisChart
                  option={monthlyOption(response, variable)}
                  label={`Monthly ${definition?.label.toLowerCase()}`}
                  height={245}
                />
              </div>
            );
          })}
        </div>
      </section>
      <section className="analysis-panel">
        <h2>Wind direction · 16 sectors</h2>
        <HelpTip label="Direction sectors">
          Raw observation counts match the retained page convention; 360° is
          treated as 0°.
        </HelpTip>
        <AnalysisChart
          option={windOption}
          label="Wind direction frequency in 16 sectors"
          height={340}
        />
        <div
          className="explore-sector-values"
          aria-label="Wind direction values"
        >
          {response.windRose.map((row) => (
            <span key={row.sector}>
              <strong>{row.sector}</strong> {row.count} ·{" "}
              {row.share == null ? "—" : `${number(row.share * 100, 1)}%`}
            </span>
          ))}
        </div>
      </section>
      </details>
      <HelpPanel label="Weather method and provenance">
        <pre>{displayJson(response.metadata)}</pre>
      </HelpPanel>
    </>
  );
}

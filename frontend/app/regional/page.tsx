"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import { registerMap } from "echarts/core";
import type { EChartsCoreOption, EChartsType } from "echarts/core";
import AnalysisChart from "@/components/analysis-chart";
import { AnalysisShell } from "@/components/analysis-shell";
import { downloadCsv, downloadJson } from "@/lib/download";
import { areas, getJson, number, shiftDay, type Coverage } from "@/lib/api";
import styles from "./regional.module.css";

const productionGroups = [
  "hydro",
  "wind",
  "solar",
  "thermal",
  "nuclear",
  "other",
];
const consumptionGroups = [
  "household",
  "cabin",
  "primary",
  "secondary",
  "tertiary",
];
const fenceTypes = ["Wyoming", "Slat-and-wire", "Solid"];

type Filters = {
  area: string;
  start: string;
  end: string;
  kind: "production" | "consumption";
  groups: string[];
  latitude: number;
  longitude: number;
  seasonStart: number;
  seasonEnd: number;
  transportDistanceM: number;
  fetchDistanceM: number;
  relocationCoefficient: number;
  fenceType: string;
};
type RegionalSummary = {
  query: {
    start: string;
    end: string;
    kind: string;
    groups: string[];
    interval: string;
  };
  unit: string;
  aggregation: string;
  areas: {
    area: string;
    meanKwh: number | null;
    observedRecords: number;
    expectedRecords: number;
    observedHours: number;
    expectedHours: number;
    partial: boolean;
  }[];
  provenance: Record<string, unknown>;
};
type SnowResult = {
  query: Record<string, unknown>;
  units: Record<string, string>;
  seasonal: {
    season: string;
    seasonLabel: string;
    qtKgPerM: number;
    qtTonnesPerM: number;
    control: string;
    fenceHeightM: number;
    observedHours: number;
    expectedHours: number;
    coveragePercent: number;
    partial: boolean;
  }[];
  monthly: {
    season: number;
    seasonLabel: string;
    seasonMonth: number;
    month: string;
    monthStart: string;
    qtKgPerM: number;
    qtTonnesPerM: number;
    control: string;
    partial: boolean;
  }[];
  directional: {
    sector: string;
    degrees: number;
    transportKgPerM: number;
    transportTonnesPerM: number;
  }[];
  averageSeasonalQtKgPerM: number;
  averageSeasonalQtTonnesPerM: number;
  averageFenceHeightM: number;
  coverage: {
    start: string;
    end: string;
    requestedStart: string;
    requestedEnd: string;
    observedHours: number;
    expectedHours: number;
    coveragePercent: number;
    partial: boolean;
  };
  sourcePreview: Record<string, unknown>[];
  provenance: Record<string, unknown>;
  method: Record<string, string>;
};

function initialFilters(coverage?: Coverage): Filters {
  const query = new URLSearchParams(window.location.search);
  const numeric = (name: string, fallback: number) => {
    const value = Number(query.get(name));
    return query.has(name) && Number.isFinite(value) ? value : fallback;
  };
  const today = coverage
    ? new Date(`${coverage.coverage.end}T00:00:00Z`)
    : new Date();
  const defaultEnd = shiftDay(today.toISOString().slice(0, 10), -1);
  const defaultStart =
    coverage?.suggestedRange.start || shiftDay(defaultEnd, -29);
  const completeSeason =
    today.getUTCMonth() >= 6
      ? today.getUTCFullYear() - 1
      : today.getUTCFullYear() - 2;
  const kind =
    query.get("kind") === "consumption" ? "consumption" : "production";
  const allowed = kind === "production" ? productionGroups : consumptionGroups;
  const groups = (
    query.get("groups") || (kind === "production" ? "solar" : "household")
  )
    .split(",")
    .filter((group) => allowed.includes(group));
  return {
    area: areas[query.get("area") || ""] ? query.get("area")! : "NO1",
    start: query.get("start") || defaultStart,
    end: query.get("end") || defaultEnd,
    kind,
    groups: groups.length ? groups : [allowed[0]],
    latitude: numeric("lat", 61.5),
    longitude: numeric("lon", 9.0),
    seasonStart: numeric("seasonStart", Math.max(2021, completeSeason - 4)),
    seasonEnd: numeric("seasonEnd", completeSeason),
    transportDistanceM: numeric("T", 3000),
    fetchDistanceM: numeric("F", 30000),
    relocationCoefficient: numeric("theta", 0.5),
    fenceType: fenceTypes.includes(query.get("fenceType") || "")
      ? query.get("fenceType")!
      : "Wyoming",
  };
}

function writeUrl(filters: Filters) {
  const query = new URLSearchParams({
    area: filters.area,
    start: filters.start,
    end: filters.end,
    kind: filters.kind,
    groups: filters.groups.join(","),
    lat: String(filters.latitude),
    lon: String(filters.longitude),
    seasonStart: String(filters.seasonStart),
    seasonEnd: String(filters.seasonEnd),
    T: String(filters.transportDistanceM),
    F: String(filters.fetchDistanceM),
    theta: String(filters.relocationCoefficient),
    fenceType: filters.fenceType,
  });
  window.history.pushState(null, "", `?${query}`);
}

function csvSnowRows(result: SnowResult) {
  return result.seasonal.map((row) => ({
    season: row.season,
    season_label: row.seasonLabel,
    qt_kg_per_m: row.qtKgPerM,
    qt_tonnes_per_m: row.qtTonnesPerM,
    control: row.control,
    fence_height_m: row.fenceHeightM,
    observed_hours: row.observedHours,
    expected_hours: row.expectedHours,
    partial: row.partial,
  }));
}

export default function RegionalPage() {
  const [filters, setFilters] = useState<Filters | null>(null);
  const [draft, setDraft] = useState<Filters | null>(null);
  const [summary, setSummary] = useState<RegionalSummary | null>(null);
  const [snow, setSnow] = useState<SnowResult | null>(null);
  const [geographyReady, setGeographyReady] = useState(false);
  const [regionalError, setRegionalError] = useState("");
  const [snowError, setSnowError] = useState("");
  const [regionalLoading, setRegionalLoading] = useState(true);
  const [snowLoading, setSnowLoading] = useState(true);

  useEffect(() => {
    let live = true;
    let coverage: Coverage | undefined;
    const restore = () => {
      const value = initialFilters(coverage);
      setFilters(value);
      setDraft(value);
    };
    getJson<Coverage>("/api/coverage")
      .then((value) => {
        if (!live) return;
        coverage = value;
        restore();
      })
      .catch(() => {
        if (live) restore();
      });
    window.addEventListener("popstate", restore);
    return () => {
      live = false;
      window.removeEventListener("popstate", restore);
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    getJson<Record<string, unknown>>(
      "/api/regional/geography",
      controller.signal,
    )
      .then((data) => {
        registerMap("norway-price-areas", data as never);
        setGeographyReady(true);
      })
      .catch((error) => {
        if (!controller.signal.aborted) setRegionalError(error.message);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!filters) return;
    const controller = new AbortController();
    setRegionalLoading(true);
    setRegionalError("");
    setSummary(null);
    const query = new URLSearchParams({
      start: filters.start,
      end: shiftDay(filters.end, 1),
      kind: filters.kind,
      groups: filters.groups.join(","),
    });
    getJson<RegionalSummary>(
      `/api/regional/summary?${query}`,
      controller.signal,
    )
      .then(setSummary)
      .catch((error) => {
        if (!controller.signal.aborted) setRegionalError(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setRegionalLoading(false);
      });
    return () => controller.abort();
  }, [filters?.start, filters?.end, filters?.kind, filters?.groups.join(",")]);

  useEffect(() => {
    if (!filters) return;
    const controller = new AbortController();
    setSnowLoading(true);
    setSnowError("");
    setSnow(null);
    fetch("/api/regional/snow-drift", {
      method: "POST",
      signal: controller.signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        latitude: filters.latitude,
        longitude: filters.longitude,
        seasonStart: filters.seasonStart,
        seasonEnd: filters.seasonEnd,
        transportDistanceM: filters.transportDistanceM,
        fetchDistanceM: filters.fetchDistanceM,
        relocationCoefficient: filters.relocationCoefficient,
        fenceType: filters.fenceType,
      }),
    })
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json().catch(() => null);
          throw new Error(
            body?.detail || "Snow-drift analysis could not be loaded.",
          );
        }
        return response.json() as Promise<SnowResult>;
      })
      .then(setSnow)
      .catch((error) => {
        if (!controller.signal.aborted) setSnowError(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setSnowLoading(false);
      });
    return () => controller.abort();
  }, [
    filters?.latitude,
    filters?.longitude,
    filters?.seasonStart,
    filters?.seasonEnd,
    filters?.transportDistanceM,
    filters?.fetchDistanceM,
    filters?.relocationCoefficient,
    filters?.fenceType,
  ]);

  function apply(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setFilters(draft);
    writeUrl(draft);
  }

  function selectPoint(latitude: number, longitude: number, area?: string) {
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
    setDraft((current) =>
      current
        ? { ...current, latitude, longitude, area: area || current.area }
        : current,
    );
    setFilters((current) => {
      if (!current) return current;
      const next = {
        ...current,
        latitude,
        longitude,
        area: area || current.area,
      };
      writeUrl(next);
      return next;
    });
  }

  const attachMap = useCallback((chart: EChartsType) => {
    chart.on("click", (raw: unknown) => {
      const event = raw as {
        name?: string;
        event?: { offsetX?: number; offsetY?: number };
      };
      const x = event.event?.offsetX;
      const y = event.event?.offsetY;
      if (x == null || y == null) return;
      const coordinate = chart.convertFromPixel({ seriesIndex: 0 }, [
        x,
        y,
      ]) as number[];
      if (
        !Array.isArray(coordinate) ||
        coordinate.length < 2 ||
        !coordinate.every(Number.isFinite)
      )
        return;
      const area = event.name?.replace(" ", "");
      selectPoint(
        Number(coordinate[1].toFixed(6)),
        Number(coordinate[0].toFixed(6)),
        areas[area || ""] ? area : undefined,
      );
    });
  }, []);

  const mapOption = useMemo<EChartsCoreOption>(() => {
    const rows = summary?.areas || [];
    const values = rows
      .map((row) => row.meanKwh)
      .filter((value): value is number => value != null);
    const min = values.length ? Math.min(...values) : 0;
    const max = values.length ? Math.max(...values) : 1;
    return {
      tooltip: {
        trigger: "item",
        formatter: (raw: unknown) => {
          const item = raw as { name: string; value?: number };
          return `${item.name}<br/>${item.value == null || Number.isNaN(item.value) ? "No valid observations" : `${number(item.value, 1)} kWh mean`}`;
        },
      },
      visualMap: {
        min,
        max: max === min ? min + 1 : max,
        left: 5,
        bottom: 5,
        text: [number(max, 0), `${number(min, 0)} kWh`],
        inRange: { color: ["#e3efe9", "#7fb5a1", "#176b59"] },
        textStyle: { color: "#607069", fontSize: 10 },
      },
      series: [
        {
          type: "map",
          map: "norway-price-areas",
          nameProperty: "ElSpotOmr",
          roam: true,
          data: rows.map((row) => ({
            name: row.area.replace("NO", "NO "),
            value: row.meanKwh,
          })),
          selectedMode: "single",
          selectedMap: filters
            ? { [filters.area.replace("NO", "NO ")]: true }
            : {},
          itemStyle: { borderColor: "#617269", borderWidth: 1 },
          emphasis: { label: { show: true } },
          select: { itemStyle: { borderColor: "#c4942f", borderWidth: 3 } },
          markPoint: filters
            ? {
                symbol: "circle",
                symbolSize: 12,
                itemStyle: {
                  color: "#c4942f",
                  borderColor: "#fff",
                  borderWidth: 2,
                },
                label: { show: false },
                data: [{ coord: [filters.longitude, filters.latitude] }],
              }
            : undefined,
        },
      ],
    };
  }, [summary, filters]);

  const seasonalOption = useMemo<EChartsCoreOption>(
    () => ({
      grid: { left: 58, right: 18, top: 28, bottom: 52 },
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: snow?.seasonal.map((row) => row.seasonLabel) || [],
        axisLabel: { rotate: 20, color: "#607069" },
      },
      yAxis: {
        type: "value",
        name: "tonnes/m",
        axisLabel: { color: "#607069" },
        splitLine: { lineStyle: { color: "#e4e9e2" } },
      },
      series: [
        {
          type: "line",
          data: snow?.seasonal.map((row) => row.qtTonnesPerM) || [],
          symbolSize: 8,
          lineStyle: { color: "#176b59", width: 3 },
          itemStyle: { color: "#176b59" },
        },
      ],
    }),
    [snow],
  );

  const monthlyAverage = useMemo(
    () =>
      Array.from({ length: 12 }, (_, index) => {
        const values =
          snow?.monthly
            .filter((row) => row.seasonMonth === index + 1)
            .map((row) => row.qtTonnesPerM) || [];
        return values.length
          ? values.reduce((sum, value) => sum + value, 0) / values.length
          : null;
      }),
    [snow],
  );
  const monthlyOption = useMemo<EChartsCoreOption>(
    () => ({
      grid: { left: 58, right: 18, top: 28, bottom: 42 },
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: [
          "Jul",
          "Aug",
          "Sep",
          "Oct",
          "Nov",
          "Dec",
          "Jan",
          "Feb",
          "Mar",
          "Apr",
          "May",
          "Jun",
        ],
        axisLabel: { color: "#607069" },
      },
      yAxis: {
        type: "value",
        name: "tonnes/m",
        axisLabel: { color: "#607069" },
        splitLine: { lineStyle: { color: "#e4e9e2" } },
      },
      series: [
        {
          type: "bar",
          data: monthlyAverage,
          itemStyle: { color: "#4b9178", borderRadius: [3, 3, 0, 0] },
        },
      ],
    }),
    [monthlyAverage],
  );
  const roseOption = useMemo<EChartsCoreOption>(
    () => ({
      tooltip: { trigger: "item", formatter: "{b}: {c} tonnes/m" },
      polar: { radius: [18, "70%"] },
      angleAxis: {
        type: "category",
        data: snow?.directional.map((row) => row.sector) || [],
        startAngle: 90,
        clockwise: true,
        axisLabel: { color: "#607069", interval: 1 },
      },
      radiusAxis: {
        name: "tonnes/m",
        axisLabel: { color: "#607069" },
        splitLine: { lineStyle: { color: "#e4e9e2" } },
      },
      series: [
        {
          type: "bar",
          coordinateSystem: "polar",
          data: snow?.directional.map((row) => row.transportTonnesPerM) || [],
          itemStyle: { color: "#176b59" },
        },
      ],
    }),
    [snow],
  );

  if (!draft || !filters)
    return (
      <AnalysisShell
        title="Regional energy & snow drift"
        description="Loading analysis controls…"
      >
        <p role="status">Loading…</p>
      </AnalysisShell>
    );
  const availableGroups =
    draft.kind === "production" ? productionGroups : consumptionGroups;
  return (
    <AnalysisShell
      title="Regional energy & snow drift"
      description="See how energy use differs across Norway, then explore how local wind and weather shape snow transport."
    >
      <form className="analysis-controls" onSubmit={apply}>
        <label>
          Energy kind
          <select
            value={draft.kind}
            onChange={(event) => {
              const kind = event.target.value as Filters["kind"];
              setDraft({
                ...draft,
                kind,
                groups: [kind === "production" ? "solar" : "household"],
              });
            }}
          >
            <option value="production">Production</option>
            <option value="consumption">Consumption</option>
          </select>
        </label>
        <label>
          Groups <span className={styles.hint}>Ctrl/Cmd for several</span>
          <select
            multiple
            value={draft.groups}
            onChange={(event) =>
              setDraft({
                ...draft,
                groups: Array.from(
                  event.target.selectedOptions,
                  (option) => option.value,
                ),
              })
            }
          >
            {availableGroups.map((group) => (
              <option key={group}>{group}</option>
            ))}
          </select>
        </label>
        <label>
          Start (UTC)
          <input
            type="date"
            required
            value={draft.start}
            onChange={(event) =>
              setDraft({ ...draft, start: event.target.value })
            }
          />
        </label>
        <label>
          End inclusive (UTC)
          <input
            type="date"
            required
            value={draft.end}
            onChange={(event) =>
              setDraft({ ...draft, end: event.target.value })
            }
          />
        </label>
        <label>
          Latitude
          <input
            type="number"
            min={-90}
            max={90}
            step="0.000001"
            required
            value={draft.latitude}
            onChange={(event) =>
              setDraft({ ...draft, latitude: Number(event.target.value) })
            }
          />
        </label>
        <label>
          Longitude
          <input
            type="number"
            min={-180}
            max={180}
            step="0.000001"
            required
            value={draft.longitude}
            onChange={(event) =>
              setDraft({ ...draft, longitude: Number(event.target.value) })
            }
          />
        </label>
        <label>
          First season
          <input
            type="number"
            min={1940}
            max={2100}
            required
            value={draft.seasonStart}
            onChange={(event) =>
              setDraft({ ...draft, seasonStart: Number(event.target.value) })
            }
          />
        </label>
        <label>
          Last season
          <input
            type="number"
            min={1940}
            max={2100}
            required
            value={draft.seasonEnd}
            onChange={(event) =>
              setDraft({ ...draft, seasonEnd: Number(event.target.value) })
            }
          />
        </label>
        <label>
          T (m)
          <input
            type="number"
            min={100}
            max={10000}
            step={100}
            required
            value={draft.transportDistanceM}
            onChange={(event) =>
              setDraft({
                ...draft,
                transportDistanceM: Number(event.target.value),
              })
            }
          />
        </label>
        <label>
          F (m)
          <input
            type="number"
            min={1000}
            max={200000}
            step={1000}
            required
            value={draft.fetchDistanceM}
            onChange={(event) =>
              setDraft({ ...draft, fetchDistanceM: Number(event.target.value) })
            }
          />
        </label>
        <label>
          Relocation θ
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            required
            value={draft.relocationCoefficient}
            onChange={(event) =>
              setDraft({
                ...draft,
                relocationCoefficient: Number(event.target.value),
              })
            }
          />
        </label>
        <label>
          Fence type
          <select
            value={draft.fenceType}
            onChange={(event) =>
              setDraft({ ...draft, fenceType: event.target.value })
            }
          >
            {fenceTypes.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={!draft.groups.length}>
          Apply analysis
        </button>
      </form>

      <div className="analysis-grid">
        <section className="analysis-panel">
          <h2>Price-area comparison</h2>
          <p>
            {summary?.aggregation || "Mean of valid hourly source records."}{" "}
            Click a region to pass that exact coordinate to snow drift; the
            coordinate fields provide full keyboard access.
          </p>
          {regionalError && (
            <p className={styles.error} role="alert">
              {regionalError}
            </p>
          )}
          {regionalLoading && (
            <p role="status">Loading regional observations…</p>
          )}
          {geographyReady && (
            <AnalysisChart
              option={mapOption}
              label={`NO1 to NO5 ${filters.kind} mean map with selected point at ${filters.latitude}, ${filters.longitude}`}
              height={500}
              onReady={attachMap}
            />
          )}
          <div
            className={styles.areaButtons}
            role="group"
            aria-label="Selected price area outline"
          >
            {Object.keys(areas).map((area) => (
              <button
                type="button"
                aria-pressed={filters.area === area}
                key={area}
                onClick={() =>
                  selectPoint(filters.latitude, filters.longitude, area)
                }
              >
                {area}
              </button>
            ))}
          </div>
        </section>
        <section className="analysis-panel">
          <h2>Regional values</h2>
          <p>
            {filters.start} through {filters.end}, inclusive UTC dates ·{" "}
            {summary?.unit || "kWh"}. Partial rows have fewer valid group-hour
            records than requested.
          </p>
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Area</th>
                  <th>Mean kWh</th>
                  <th>Coverage</th>
                </tr>
              </thead>
              <tbody>
                {summary?.areas.map((row) => (
                  <tr key={row.area}>
                    <th>{row.area}</th>
                    <td>{number(row.meanKwh, 1)}</td>
                    <td>
                      {row.observedRecords.toLocaleString("en-GB")} /{" "}
                      {row.expectedRecords.toLocaleString("en-GB")}
                      {row.partial ? " · partial" : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="analysis-actions">
            <button
              type="button"
              disabled={!summary}
              onClick={() =>
                summary &&
                downloadCsv(
                  `regional-${filters.start}-${filters.end}.csv`,
                  summary.areas,
                )
              }
            >
              Download displayed CSV
            </button>
            <button
              type="button"
              disabled={!summary}
              onClick={() =>
                summary &&
                downloadJson(
                  `regional-${filters.start}-${filters.end}-metadata.json`,
                  summary,
                )
              }
            >
              Download data + metadata JSON
            </button>
          </div>
          {summary && (
            <details>
              <summary>Source and aggregation metadata</summary>
              <pre>
                {JSON.stringify(
                  {
                    query: summary.query,
                    aggregation: summary.aggregation,
                    unit: summary.unit,
                    provenance: summary.provenance,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          )}
        </section>
      </div>

      <section className="analysis-panel">
        <h2>
          Tabler transport at {filters.latitude.toFixed(5)},{" "}
          {filters.longitude.toFixed(5)}
        </h2>
        <p>
          This calculation uses ERA5-Seamless weather at the selected
          coordinate, not the fixed city proxy used by area weather views.
          Seasons run July through June. Partial seasons remain visible and
          labeled.
        </p>
        <p className={styles.methodNote}>
          Tabler transport is a statistical estimate. Fence height is an
          indicative storage calculation and is not a site-specific engineering
          design.
        </p>
        {snowError && (
          <p className={styles.error} role="alert">
            {snowError}
          </p>
        )}
        {snowLoading && (
          <p role="status">Loading point weather and calculating transport…</p>
        )}
        {snow && (
          <>
            <div className={`analysis-metrics ${styles.metrics}`}>
              <div>
                <span>Average seasonal Qt</span>
                <strong>
                  {number(snow.averageSeasonalQtTonnesPerM, 2)} t/m
                </strong>
              </div>
              <div>
                <span>Indicative {filters.fenceType} height</span>
                <strong>{number(snow.averageFenceHeightM, 2)} m</strong>
              </div>
              <div>
                <span>Weather coverage</span>
                <strong>{number(snow.coverage.coveragePercent, 1)}%</strong>
                <small>
                  {snow.coverage.partial
                    ? "Partial requested interval"
                    : "Complete requested interval"}
                </small>
              </div>
            </div>
            <div className="analysis-grid">
              <div>
                <h3>Seasonal transport</h3>
                <AnalysisChart
                  option={seasonalOption}
                  label="Seasonal Tabler snow transport in tonnes per metre"
                />
              </div>
              <div>
                <h3>Average monthly transport</h3>
                <AnalysisChart
                  option={monthlyOption}
                  label="Average monthly Tabler snow transport from July through June"
                />
              </div>
            </div>
            <div className="analysis-grid">
              <div>
                <h3>Directional wind potential</h3>
                <AnalysisChart
                  option={roseOption}
                  label="Sixteen-sector potential wind-driven snow transport rose"
                />
              </div>
              <div>
                <h3>Season detail</h3>
                <div className={styles.tableWrap}>
                  <table>
                    <thead>
                      <tr>
                        <th>Season</th>
                        <th>Qt t/m</th>
                        <th>Control</th>
                        <th>Fence m</th>
                      </tr>
                    </thead>
                    <tbody>
                      {snow.seasonal.map((row) => (
                        <tr key={row.season}>
                          <th>{row.seasonLabel}</th>
                          <td>{number(row.qtTonnesPerM, 3)}</td>
                          <td>{row.control}</td>
                          <td>{number(row.fenceHeightM, 2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            <div className="analysis-actions">
              <button
                type="button"
                onClick={() =>
                  downloadCsv(
                    `snow-drift-${filters.latitude}-${filters.longitude}.csv`,
                    csvSnowRows(snow),
                  )
                }
              >
                Download seasonal CSV
              </button>
              <button
                type="button"
                onClick={() =>
                  downloadCsv(
                    `snow-drift-monthly-${filters.latitude}-${filters.longitude}.csv`,
                    snow.monthly,
                  )
                }
              >
                Download monthly CSV
              </button>
              <button
                type="button"
                onClick={() =>
                  downloadJson(
                    `snow-drift-${filters.latitude}-${filters.longitude}-metadata.json`,
                    snow,
                  )
                }
              >
                Download full data + metadata JSON
              </button>
            </div>
            <details>
              <summary>Monthly transport by season</summary>
              <div className={styles.tableWrap}>
                <table>
                  <thead>
                    <tr>
                      <th>Season</th>
                      <th>Month</th>
                      <th>Qt t/m</th>
                      <th>Control</th>
                      <th>Coverage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snow.monthly.map((row) => (
                      <tr key={`${row.season}-${row.seasonMonth}`}>
                        <th>{row.seasonLabel}</th>
                        <td>{row.month}</td>
                        <td>{number(row.qtTonnesPerM, 3)}</td>
                        <td>{row.control}</td>
                        <td>{row.partial ? "Partial" : "Complete"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
            <details>
              <summary>Method, units, and engineering limitation</summary>
              <pre>
                {JSON.stringify(
                  {
                    query: snow.query,
                    units: snow.units,
                    method: snow.method,
                    coverage: snow.coverage,
                    provenance: snow.provenance,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
            <details>
              <summary>First 24 point-weather source rows</summary>
              <div className={styles.tableWrap}>
                <table>
                  <thead>
                    <tr>
                      {snow.sourcePreview[0] &&
                        Object.keys(snow.sourcePreview[0]).map((key) => (
                          <th key={key}>{key}</th>
                        ))}
                    </tr>
                  </thead>
                  <tbody>
                    {snow.sourcePreview.map((row, index) => (
                      <tr key={index}>
                        {Object.values(row).map((value, cell) => (
                          <td key={cell}>{String(value ?? "")}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </>
        )}
      </section>
    </AnalysisShell>
  );
}

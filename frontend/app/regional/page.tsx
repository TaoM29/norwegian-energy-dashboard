"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { registerMap } from "echarts/core";
import type { EChartsCoreOption, EChartsType } from "echarts/core";
import AnalysisChart from "@/components/analysis-chart";
import { AnalysisShell } from "@/components/analysis-shell";
import { ExportMenu } from "@/components/export-menu";
import { downloadCsv, downloadJson } from "@/lib/download";
import { areas, getJson, number, shiftDay, type Coverage } from "@/lib/api";
import { DateRangePicker, parseDate } from "@/components/date-range-picker";
import { AppliedFilters } from "@/components/applied-filters";
import { HelpPanel, HelpTip } from "@/components/help";
import { Select } from "@/components/ui/select";
import { writeDashboardUrl } from "@/lib/navigation-state";
import { RegionalPeaksView, type RegionalPeaks } from "@/components/demand-peaks";
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

type Mode = "energy" | "peaks" | "snow";
type Filters = {
  mode: Mode;
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
  const availableEnd = coverage
    ? shiftDay(coverage.coverage.end, -1)
    : defaultEnd;
  const requestedStart = query.get("start") || defaultStart;
  const start =
    !parseDate(requestedStart) ||
    (coverage &&
      (requestedStart < coverage.coverage.start ||
        requestedStart > availableEnd))
      ? defaultStart
      : requestedStart;
  const requestedEnd = query.get("end") || defaultEnd;
  const end =
    !parseDate(requestedEnd) ||
    requestedEnd < start ||
    (coverage && requestedEnd > availableEnd)
      ? defaultEnd < start
        ? start
        : defaultEnd
      : requestedEnd;
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
  const requestedMode = query.get("mode");
  const mode: Mode =
    requestedMode === "snow" ||
    (!requestedMode &&
      (query.has("lat") || query.has("lon") || query.has("seasonStart")))
      ? "snow"
      : requestedMode === "peaks" ? "peaks" : "energy";
  return {
    mode,
    area: areas[query.get("area") || ""] ? query.get("area")! : "NO1",
    start,
    end,
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

function writeUrl(filters: Filters, replace = false) {
  const query = new URLSearchParams({
    mode: filters.mode,
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
  writeDashboardUrl(`?${query}`, { replace });
}

function energyChanged(draft: Filters, applied: Filters) {
  return (
    draft.area !== applied.area ||
    draft.start !== applied.start ||
    draft.end !== applied.end ||
    draft.kind !== applied.kind ||
    draft.groups.join(",") !== applied.groups.join(",")
  );
}

function snowChanged(draft: Filters, applied: Filters) {
  return (
    draft.latitude !== applied.latitude ||
    draft.longitude !== applied.longitude ||
    draft.seasonStart !== applied.seasonStart ||
    draft.seasonEnd !== applied.seasonEnd ||
    draft.transportDistanceM !== applied.transportDistanceM ||
    draft.fetchDistanceM !== applied.fetchDistanceM ||
    draft.relocationCoefficient !== applied.relocationCoefficient ||
    draft.fenceType !== applied.fenceType
  );
}

function peaksChanged(draft: Filters, applied: Filters) {
  return draft.start !== applied.start || draft.end !== applied.end;
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
  const filtersRef = useRef<Filters | null>(null);
  const [coverageBounds, setCoverageBounds] = useState<Coverage | null>(null);
  const [draft, setDraft] = useState<Filters | null>(null);
  const [summary, setSummary] = useState<RegionalSummary | null>(null);
  const [peaks, setPeaks] = useState<RegionalPeaks | null>(null);
  const [peaksError, setPeaksError] = useState("");
  const [peaksLoading, setPeaksLoading] = useState(false);
  const [snow, setSnow] = useState<SnowResult | null>(null);
  const [geographyReady, setGeographyReady] = useState(false);
  const [regionalError, setRegionalError] = useState("");
  const [snowError, setSnowError] = useState("");
  const [regionalLoading, setRegionalLoading] = useState(false);
  const [snowLoading, setSnowLoading] = useState(false);
  const [requestRevision, setRequestRevision] = useState(0);

  useEffect(() => {
    let live = true;
    let coverage: Coverage | undefined;
    const restore = () => {
      const value = initialFilters(coverage);
      filtersRef.current = value;
      setFilters(value);
      setDraft(value);
      setRegionalLoading(value.mode === "energy");
      setPeaksLoading(value.mode === "peaks");
      setSnowLoading(value.mode === "snow");
      writeUrl(value, true);
    };
    getJson<Coverage>("/api/coverage")
      .then((value) => {
        if (!live) return;
        coverage = value;
        setCoverageBounds(value);
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
    if (!filters || filters.mode !== "energy" || geographyReady) return;
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
  }, [filters?.mode, geographyReady]);

  useEffect(() => {
    if (!filters || filters.mode !== "energy") {
      setRegionalLoading(false);
      return;
    }
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
  }, [
    filters?.mode,
    filters?.start,
    filters?.end,
    filters?.kind,
    filters?.groups.join(","),
    requestRevision,
  ]);

  useEffect(() => {
    if (!filters || filters.mode !== "peaks") {
      setPeaksLoading(false);
      return;
    }
    const controller = new AbortController();
    setPeaksLoading(true);
    setPeaksError("");
    setPeaks(null);
    const query = new URLSearchParams({ start: filters.start, end: shiftDay(filters.end, 1) });
    getJson<RegionalPeaks>(`/api/regional/demand-peaks?${query}`, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setPeaks(value); })
      .catch((error) => { if (!controller.signal.aborted) setPeaksError(error.message); })
      .finally(() => { if (!controller.signal.aborted) setPeaksLoading(false); });
    return () => controller.abort();
  }, [filters?.mode, filters?.start, filters?.end, requestRevision]);

  useEffect(() => {
    if (!filters || filters.mode !== "snow") {
      setSnowLoading(false);
      return;
    }
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
    filters?.mode,
    filters?.latitude,
    filters?.longitude,
    filters?.seasonStart,
    filters?.seasonEnd,
    filters?.transportDistanceM,
    filters?.fetchDistanceM,
    filters?.relocationCoefficient,
    filters?.fenceType,
    requestRevision,
  ]);

  function apply(event: FormEvent) {
    event.preventDefault();
    if (!draft || !filters) return;
    if (draft.mode === "peaks" && (Date.parse(`${shiftDay(draft.end, 1)}T00:00:00Z`) - Date.parse(`${draft.start}T00:00:00Z`)) / 86400000 > 366) {
      setPeaksError("Peak comparison supports up to 366 inclusive dates. Choose a shorter range.");
      return;
    }
    const next: Filters =
      draft.mode === "energy"
        ? {
            ...filters,
            mode: "energy",
            area: draft.area,
            start: draft.start,
            end: draft.end,
            kind: draft.kind,
            groups: draft.groups,
          }
        : draft.mode === "peaks" ? {
            ...filters,
            mode: "peaks",
            start: draft.start,
            end: draft.end,
          } : {
            ...filters,
            mode: "snow",
            latitude: draft.latitude,
            longitude: draft.longitude,
            seasonStart: draft.seasonStart,
            seasonEnd: draft.seasonEnd,
            transportDistanceM: draft.transportDistanceM,
            fetchDistanceM: draft.fetchDistanceM,
            relocationCoefficient: draft.relocationCoefficient,
            fenceType: draft.fenceType,
          };
    filtersRef.current = next;
    setFilters(next);
    setRegionalLoading(next.mode === "energy");
    setPeaksLoading(next.mode === "peaks");
    setSnowLoading(next.mode === "snow");
    setRequestRevision((value) => value + 1);
    writeUrl(next);
  }

  function chooseMode(mode: Mode) {
    if (!draft || !filters || mode === filters.mode) return;
    const next = { ...filters, mode };
    filtersRef.current = next;
    setFilters(next);
    setDraft({ ...draft, mode });
    setRegionalError("");
    setPeaksError("");
    setSnowError("");
    setRegionalLoading(mode === "energy");
    setPeaksLoading(mode === "peaks");
    setSnowLoading(mode === "snow");
    writeUrl(next);
  }

  function selectPoint(latitude: number, longitude: number, area?: string) {
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
    setDraft((current) =>
      current
        ? { ...current, latitude, longitude, area: area || current.area }
        : current,
    );
    const current = filtersRef.current;
    if (!current) return;
    const next = {
      ...current,
      latitude,
      longitude,
      area: area || current.area,
    };
    filtersRef.current = next;
    setFilters(next);
    writeUrl(next);
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
        title="Regional analysis"
        description="Loading analysis controls…"
      >
        <p role="status">Loading…</p>
      </AnalysisShell>
    );
  const availableGroups =
    draft.kind === "production" ? productionGroups : consumptionGroups;
  return (
    <AnalysisShell
      title="Regional analysis"
      description="Compare energy and household demand across price areas, or estimate wind-driven snow transport."
    >
      <div
        className={styles.modeSwitch}
        role="tablist"
        aria-label="Regional analysis"
      >
        {(["energy", "peaks", "snow"] as Mode[]).map((mode) => (
          <button
            id={`regional-${mode}-tab`}
            key={mode}
            type="button"
            role="tab"
            aria-selected={filters.mode === mode}
            aria-controls={`regional-${mode}-panel`}
            tabIndex={filters.mode === mode ? 0 : -1}
            onClick={() => chooseMode(mode)}
            onKeyDown={(event) => {
              if (![
                "ArrowLeft",
                "ArrowRight",
                "Home",
                "End",
              ].includes(event.key))
                return;
              event.preventDefault();
              const modes: Mode[] = ["energy", "peaks", "snow"];
              const position = modes.indexOf(mode);
              const next = event.key === "Home" ? modes[0] : event.key === "End" ? modes[modes.length - 1] : modes[(position + (event.key === "ArrowRight" ? 1 : -1) + modes.length) % modes.length];
              chooseMode(next);
              requestAnimationFrame(() =>
                document.getElementById(`regional-${next}-tab`)?.focus(),
              );
            }}
          >
            {mode === "energy" ? "Energy comparison" : mode === "peaks" ? "Demand peaks" : "Snow model"}
          </button>
        ))}
      </div>

      {filters.mode === "energy" ? (
        <>
          <div className={styles.modeIntro}>
            <strong>Compare NO1–NO5</strong>
            <HelpTip label="Comparison scope">
              Choose production or consumption groups and one inclusive UTC
              date range. Every price area uses the same selection.
            </HelpTip>
          </div>
          <form
            id="regional-energy-panel"
            role="tabpanel"
            aria-labelledby="regional-energy-tab"
            className="analysis-controls"
            onSubmit={apply}
          >
            <label>
              Energy kind
              <Select
                aria-label="Energy kind"
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
              </Select>
            </label>
            <details className={styles.filterDetails}>
              <summary>Energy groups · {draft.groups.length} selected</summary>
            <fieldset className={styles.groupChoices}>
              <legend>Energy groups</legend>
              <div>
                {availableGroups.map((group) => (
                  <label key={group}>
                    <input
                      type="checkbox"
                      checked={draft.groups.includes(group)}
                      onChange={(event) =>
                        setDraft({
                          ...draft,
                          groups: event.target.checked
                            ? availableGroups.filter(
                                (item) =>
                                  item === group || draft.groups.includes(item),
                              )
                            : draft.groups.filter((item) => item !== group),
                        })
                      }
                    />
                    {group}
                  </label>
                ))}
              </div>
            </fieldset>
            </details>
            <DateRangePicker
              value={{ start: draft.start, end: draft.end }}
              min={coverageBounds?.coverage.start}
              max={
                coverageBounds
                  ? shiftDay(coverageBounds.coverage.end, -1)
                  : undefined
              }
              onChange={(range) => setDraft({ ...draft, ...range })}
            />
            <button type="submit" disabled={!draft.groups.length}>
              Compare energy
            </button>
          </form>
          <AppliedFilters
            dirty={energyChanged(draft, filters)}
            loading={regionalLoading}
            onReset={() =>
              setDraft({
                ...draft,
                area: filters.area,
                start: filters.start,
                end: filters.end,
                kind: filters.kind,
                groups: filters.groups,
              })
            }
          />
        </>
      ) : filters.mode === "peaks" ? (
        <>
          <form id="regional-peaks-panel" role="tabpanel" aria-labelledby="regional-peaks-tab" className="analysis-controls" onSubmit={apply}>
            <DateRangePicker
              value={{ start: draft.start, end: draft.end }}
              min={coverageBounds?.coverage.start}
              max={coverageBounds ? shiftDay(coverageBounds.coverage.end, -1) : undefined}
              onChange={(range) => setDraft({ ...draft, ...range })}
            />
            <button type="submit">Compare matched hours</button>
          </form>
          <AppliedFilters
            dirty={peaksChanged(draft, filters)}
            loading={peaksLoading}
            onReset={() => setDraft({ ...draft, start: filters.start, end: filters.end })}
          />
        </>
      ) : (
        <>
          <div className={styles.modeIntro}>
            <strong>Estimate snow transport</strong>
            <HelpTip label="Snow model scope">
              Set the site, July–June seasons, transport assumptions, and fence
              type. This model does not use the energy comparison dates.
            </HelpTip>
          </div>
          <form
            id="regional-snow-panel"
            role="tabpanel"
            aria-labelledby="regional-snow-tab"
            className="analysis-controls"
            onSubmit={apply}
          >
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
              First July–June season
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
              Last July–June season
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
            <details className={styles.filterDetails}>
              <summary>Model assumptions · {draft.fenceType}</summary>
              <div className={styles.filterBody}>
            <label>
              Transport distance T (m)
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
              Fetch distance F (m)
              <input
                type="number"
                min={1000}
                max={200000}
                step={1000}
                required
                value={draft.fetchDistanceM}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    fetchDistanceM: Number(event.target.value),
                  })
                }
              />
            </label>
            <label>
              Relocation coefficient θ
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
              <Select
                aria-label="Fence type"
                value={draft.fenceType}
                onChange={(event) =>
                  setDraft({ ...draft, fenceType: event.target.value })
                }
              >
                {fenceTypes.map((name) => (
                  <option key={name}>{name}</option>
                ))}
              </Select>
            </label>
              </div>
            </details>
            <button type="submit">Run snow model</button>
          </form>
          <div
            className={styles.appliedModel}
            data-pending={snowChanged(draft, filters) && !snowLoading}
          >
            <span role="status">
              {snowLoading
                ? "Updating result…"
                : snowChanged(draft, filters)
                  ? "Changes not applied"
                  : "Model settings applied"}
            </span>
            {snowChanged(draft, filters) && !snowLoading && (
              <button
                type="button"
                onClick={() =>
                  setDraft({
                    ...draft,
                    latitude: filters.latitude,
                    longitude: filters.longitude,
                    seasonStart: filters.seasonStart,
                    seasonEnd: filters.seasonEnd,
                    transportDistanceM: filters.transportDistanceM,
                    fetchDistanceM: filters.fetchDistanceM,
                    relocationCoefficient: filters.relocationCoefficient,
                    fenceType: filters.fenceType,
                  })
                }
              >
                Discard changes
              </button>
            )}
          </div>
        </>
      )}

      {filters.mode === "energy" && (
      <div className={styles.regionalFlow}>
        <section className="analysis-panel">
          <h2>Price-area comparison</h2>
          <p className={styles.mapScope}>{summary?.aggregation || "Mean of valid hourly source records."}</p>
          {summary?.areas.some((row) => row.partial) && (
            <p className={styles.partialCoverage} role="note">
              Partial coverage in {summary.areas.filter((row) => row.partial).map((row) => row.area).join(", ")}. Open regional values and coverage for counts.
            </p>
          )}
          <HelpTip label="Using the map">
            Select a region or map point, then open Snow model to use that
            coordinate. The regional table compares all five price areas.
          </HelpTip>
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
              exports={
                summary ? (
                  <>
                    <button
                      type="button"
                      onClick={() =>
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
                      onClick={() =>
                        downloadJson(
                          `regional-${filters.start}-${filters.end}-metadata.json`,
                          summary,
                        )
                      }
                    >
                      Download data + metadata JSON
                    </button>
                  </>
                ) : null
              }
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
        <details className={styles.secondaryAnalysis}>
          <summary>Regional values and coverage</summary>
        <section className="analysis-panel">
          <h2>Regional values</h2>
          <p>
            {filters.start} through {filters.end}, inclusive UTC dates ·{" "}
            {summary?.unit || "kWh"}.
          </p>
          <HelpTip label="Regional coverage">
            Partial rows have fewer valid group-hour records than requested.
          </HelpTip>
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
          {summary && (
            <ExportMenu>
              <button
                type="button"
                onClick={() =>
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
                onClick={() =>
                  downloadJson(
                    `regional-${filters.start}-${filters.end}-metadata.json`,
                    summary,
                  )
                }
              >
                Download data + metadata JSON
              </button>
            </ExportMenu>
          )}
          {summary && (
            <HelpPanel label="Source and aggregation metadata">
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
            </HelpPanel>
          )}
        </section>
        </details>
      </div>
      )}

      {filters.mode === "peaks" && (
        <>
          {peaksLoading && <section className="analysis-panel" role="status">Loading matched household demand…</section>}
          {peaksError && <section className="analysis-panel" role="alert"><p className={styles.error}>{peaksError}</p><button type="button" onClick={() => setRequestRevision((value) => value + 1)}>Try again</button></section>}
          {!peaksLoading && !peaksError && peaks && <RegionalPeaksView result={peaks} />}
        </>
      )}

      {filters.mode === "snow" && (
      <section className="analysis-panel">
        <h2>
          Tabler transport at {filters.latitude.toFixed(5)},{" "}
          {filters.longitude.toFixed(5)}
        </h2>
        <p>ERA5-Seamless point weather · July–June seasons.</p>
        <HelpTip label="Location and seasons">
          The calculation uses weather at the selected coordinate instead of
          the fixed city proxy used by area weather views. Partial seasons
          remain visible and labeled.
        </HelpTip>
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
            <div className={styles.regionalFlow}>
              <div>
                <h3>Seasonal transport</h3>
                <AnalysisChart
                  option={seasonalOption}
                  label="Seasonal Tabler snow transport in tonnes per metre"
                  exports={
                    <>
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
                          downloadJson(
                            `snow-drift-${filters.latitude}-${filters.longitude}-metadata.json`,
                            snow,
                          )
                        }
                      >
                        Download full data + metadata JSON
                      </button>
                    </>
                  }
                />
              </div>
              <details className={styles.secondaryAnalysis}>
                <summary>Monthly transport</summary>
              <div>
                <h3>Average monthly transport</h3>
                <AnalysisChart
                  option={monthlyOption}
                  label="Average monthly Tabler snow transport from July through June"
                  exports={
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
                  }
                />
              </div>
              </details>
            </div>
            <details className={styles.secondaryAnalysis}>
              <summary>Wind and season detail</summary>
            <div className="analysis-grid">
              <div>
                <h3>Directional wind potential</h3>
                <AnalysisChart
                  option={roseOption}
                  label="Sixteen-sector potential wind-driven snow transport rose"
                  exports={
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
                  }
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
            </details>
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
            <HelpPanel label="Method, units, and engineering limitation">
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
            </HelpPanel>
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
      )}
    </AnalysisShell>
  );
}

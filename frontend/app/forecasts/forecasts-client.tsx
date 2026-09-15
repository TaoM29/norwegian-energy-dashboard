"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import type { EChartsCoreOption } from "echarts/core";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Database,
  Play,
  Square,
} from "lucide-react";
import AnalysisChart from "@/components/analysis-chart";
import { AnalysisShell } from "@/components/analysis-shell";
import { areas, number } from "@/lib/api";
import { downloadCsv, downloadJson } from "@/lib/download";
import styles from "./forecasts.module.css";

const benchmarkModels = [
  "seasonal_naive",
  "ridge",
  "gradient_boosting",
  "sarimax",
];
const modelLabels: Record<string, string> = {
  baseline: "Seasonal baseline",
  seasonal_naive: "Seasonal baseline",
  ridge: "Ridge",
  gradient_boosting: "Gradient boosting",
  gradientboosting: "Gradient boosting",
  gb: "Gradient boosting",
  sarimax: "SARIMAX",
  sarimax_no_exog: "SARIMAX without weather",
  sarimax_exog: "SARIMAX with weather",
};
const seriesColours = ["#176b59", "#d4774d", "#725f9e", "#3f7eaa", "#a55366"];
const weatherVariables = [
  ["temperature_2m (°C)", "Temperature (2 m)"],
  ["precipitation (mm)", "Precipitation"],
  ["wind_speed_10m (m/s)", "Wind speed (10 m)"],
  ["wind_gusts_10m (m/s)", "Wind gusts (10 m)"],
  ["wind_direction_10m (°)", "Wind direction (10 m)"],
] as const;
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

type Json = Record<string, unknown>;
type ResultSummary = {
  id: string;
  kind: "evaluation" | "sarimax";
  title: string;
  createdAt: string;
  issueTime: string | null;
  areas: string[];
  start: string | null;
  end: string | null;
  horizon: number | null;
  models: string[];
  weatherMode: string | null;
  sourceLabel: string | null;
  metadata: Json;
};
type Job = {
  id: string;
  kind: "evaluation" | "sarimax";
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  config: Json;
  progress: number;
  message: string | null;
  error: string | null;
  resultId: string | null;
  createdAt: string;
  updatedAt: string;
  startedAt: string | null;
  completedAt: string | null;
  limits: Json;
};
type ForecastResult = Json & {
  id: string;
  kind: "evaluation" | "sarimax";
  title: string;
  createdAt: string;
  metadata?: Json;
  config?: Json;
  predictions?: Json[];
  metrics?: Json[];
  forecast?: Json[];
  training?: Json[];
  backtest?: { metrics?: Json[]; predictions?: Json[]; failures?: Json[] };
  failures?: Json[];
};
type ViewState = {
  result: string;
  job: string;
  area: string;
  start: string;
  end: string;
  models: string[];
  split: string;
  dimension: string;
  origin: string;
};
type EvaluationDraft = {
  areas: string[];
  models: string[];
  horizon: number;
  trainDays: number;
  validationOrigins: string;
  calibrationOrigins: string;
  holdoutOrigins: string;
  weatherMode: "historical_only" | "realized_future_upper_bound";
  energyLag: number;
  weatherLag: number;
  coverage: number;
  randomSeed: number;
};
type SarimaxDraft = {
  area: string;
  kind: "production" | "consumption";
  group: string;
  start: string;
  end: string;
  frequency: "h" | "D";
  horizon: number;
  order: [number, number, number];
  seasonal: boolean;
  seasonalOrder: [number, number, number, number];
  weatherVariables: string[];
  futureWeather: "last" | "hod-mean";
  dynamic: boolean;
  dynamicStart: number;
  backtest: boolean;
  baselineLag: number;
  backtestHorizon: number;
  step: number;
  folds: number;
  energyLagHours: number;
  weatherLagHours: number;
  evalNoExog: boolean;
};

function initialView(): ViewState {
  const query = new URLSearchParams(window.location.search);
  return {
    result: query.get("result") || "",
    job: query.get("job") || "",
    area: areas[query.get("area") || ""] ? query.get("area")! : "NO1",
    start: query.get("start") || "",
    end: query.get("end") || "",
    models: (query.get("models") || "").split(",").filter(Boolean),
    split: query.get("split") || "holdout",
    dimension: query.get("dimension") || "overall",
    origin: query.get("origin") || "",
  };
}

function defaultEvaluation(): EvaluationDraft {
  return {
    areas: Object.keys(areas),
    models: [...benchmarkModels],
    horizon: 24,
    trainDays: 120,
    validationOrigins: "2025-09-01, 2025-09-15",
    calibrationOrigins: "2025-10-01, 2025-10-15",
    holdoutOrigins: "2025-11-01, 2025-12-01",
    weatherMode: "historical_only",
    energyLag: 48,
    weatherLag: 120,
    coverage: 0.8,
    randomSeed: 320,
  };
}

function defaultSarimax(): SarimaxDraft {
  return {
    area: "NO1",
    kind: "production",
    group: "hydro",
    start: "2025-01-01",
    end: "2025-04-01",
    frequency: "h",
    horizon: 24,
    order: [1, 1, 1],
    seasonal: true,
    seasonalOrder: [1, 0, 1, 24],
    weatherVariables: [],
    futureWeather: "last",
    dynamic: true,
    dynamicStart: 0.7,
    backtest: true,
    baselineLag: 168,
    backtestHorizon: 24,
    step: 24,
    folds: 3,
    energyLagHours: 48,
    weatherLagHours: 120,
    evalNoExog: true,
  };
}

function asObject(value: unknown): Json {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Json)
    : {};
}

function asRows(value: unknown): Json[] {
  return Array.isArray(value)
    ? value.filter((row): row is Json => !!row && typeof row === "object")
    : [];
}

function textValue(row: Json, ...keys: string[]) {
  for (const key of keys) {
    const value = row[key];
    if (typeof value === "string" && value) return value;
  }
  return "";
}

function numericValue(row: Json, ...keys: string[]): number | null {
  for (const key of keys) {
    const value = row[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

function nestedValue(root: Json | undefined, paths: string[]): unknown {
  for (const path of paths) {
    let value: unknown = root;
    for (const part of path.split(".")) value = asObject(value)[part];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return null;
}

function normalizeModel(model: string) {
  const key = model.toLowerCase().replaceAll(" ", "_").replaceAll("-", "_");
  if (key.includes("seasonal_naive")) return "seasonal_naive";
  if (key.includes("sarimax") && key.includes("no_exog"))
    return "sarimax_no_exog";
  if (
    key.includes("sarimax") &&
    (key.includes("+exog") || key.includes("with_weather"))
  )
    return "sarimax_exog";
  if (key === "sarimax") return "sarimax";
  if (["gradient_boosting", "gradientboosting", "gb"].includes(key))
    return "gradient_boosting";
  if (key === "baseline") return "seasonal_naive";
  return key;
}

function modelKey(row: Json) {
  return normalizeModel(
    textValue(row, "model", "modelName", "name") || "sarimax",
  );
}

function modelLabel(model: string) {
  const key = model.toLowerCase().replaceAll(" ", "_").replaceAll("-", "_");
  return modelLabels[key] || model.replaceAll("_", " ");
}

function splitKey(row: Json) {
  return (
    textValue(row, "split", "dataset", "partition", "foldType", "cohort") ||
    "holdout"
  );
}

function explicitSplit(row: Json) {
  return textValue(row, "split", "dataset", "partition", "foldType", "cohort");
}

function originKey(row: Json) {
  return textValue(row, "origin", "forecastOrigin", "issueTime", "cutoff");
}

function targetTime(row: Json) {
  return textValue(row, "targetTime", "time", "timestamp", "date");
}

function areaKey(row: Json) {
  return textValue(row, "area", "priceArea") || "NO1";
}

function formatDateTime(value: unknown) {
  if (typeof value !== "string" || !value) return "Unavailable";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat("en-GB", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "UTC",
      }).format(date) + " UTC";
}

function shortUtcTick(value: string) {
  return value.length >= 16
    ? `${value.slice(5, 10)}\n${value.slice(11, 16)}`
    : value;
}

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Request failed (${response.status})`,
    );
  }
  return response.json();
}

function csvRows(rows: Json[]) {
  return rows.map((row) => ({ ...row })) as Record<string, unknown>[];
}

function ResultStatus({ job }: { job: Job }) {
  const Icon =
    job.status === "succeeded"
      ? CheckCircle2
      : job.status === "failed"
        ? AlertTriangle
        : Clock3;
  return (
    <div className={styles.jobStatus} data-state={job.status} role="status">
      <Icon size={18} aria-hidden="true" />
      <div>
        <strong>
          {job.kind === "evaluation"
            ? "Benchmark evaluation"
            : "Custom SARIMAX"}{" "}
          · {job.status}
        </strong>
        <span>
          {job.message ||
            job.error ||
            `Updated ${formatDateTime(job.updatedAt)}`}
        </span>
      </div>
      <span className={styles.progressValue}>
        {Math.round(Math.max(0, Math.min(1, job.progress)) * 100)}%
      </span>
      <div
        className={styles.progressTrack}
        aria-label={`${Math.round(job.progress * 100)}% complete`}
      >
        <span
          style={{ width: `${Math.max(0, Math.min(1, job.progress)) * 100}%` }}
        />
      </div>
    </div>
  );
}

export default function ForecastsClient() {
  const [view, setView] = useState<ViewState | null>(null);
  const [results, setResults] = useState<ResultSummary[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [detail, setDetail] = useState<ForecastResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [jobError, setJobError] = useState("");
  const [runningAction, setRunningAction] = useState(false);
  const [customJobsEnabled, setCustomJobsEnabled] = useState(false);
  const [evaluation, setEvaluation] = useState(defaultEvaluation);
  const [sarimax, setSarimax] = useState(defaultSarimax);

  const updateView = useCallback(
    (patch: Partial<ViewState>, replace = false) => {
      setView((current) => {
        if (!current) return current;
        const next = { ...current, ...patch };
        const params = new URLSearchParams();
        if (next.result) params.set("result", next.result);
        if (next.job) params.set("job", next.job);
        params.set("area", next.area);
        if (next.start) params.set("start", next.start);
        if (next.end) params.set("end", next.end);
        if (next.models.length) params.set("models", next.models.join(","));
        params.set("split", next.split);
        params.set("dimension", next.dimension);
        if (next.origin) params.set("origin", next.origin);
        window.history[replace ? "replaceState" : "pushState"](
          null,
          "",
          `?${params}`,
        );
        return next;
      });
    },
    [],
  );

  useEffect(() => {
    apiJson<{ customJobsEnabled: boolean }>("/api/forecasts/capabilities")
      .then((value) => setCustomJobsEnabled(value.customJobsEnabled))
      .catch(() => setCustomJobsEnabled(false));
  }, []);

  const loadLists = useCallback(async () => {
    const [resultResponse, jobResponse] = await Promise.all([
      apiJson<{ items: ResultSummary[] }>("/api/forecasts/results"),
      apiJson<{ items: Job[] }>("/api/forecasts/jobs"),
    ]);
    setResults(resultResponse.items);
    setJobs(jobResponse.items);
    return { results: resultResponse.items, jobs: jobResponse.items };
  }, []);

  useEffect(() => {
    const restore = () => setView(initialView());
    restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);

  useEffect(() => {
    if (!view) return;
    let live = true;
    setLoading(true);
    setError("");
    loadLists()
      .then(({ results: loaded }) => {
        if (!live) return;
        const selected = loaded.some((item) => item.id === view.result)
          ? view.result
          : loaded.find((item) => item.kind === "evaluation")?.id ||
            loaded[0]?.id ||
            "";
        if (selected !== view.result) updateView({ result: selected }, true);
        if (!selected) setLoading(false);
      })
      .catch((reason: Error) => {
        if (live) {
          setError(reason.message);
          setLoading(false);
        }
      });
    return () => {
      live = false;
    };
    // Initial list load. Selection changes are handled by the detail effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view ? "ready" : "waiting", loadLists, updateView]);

  useEffect(() => {
    if (!view?.result) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError("");
    apiJson<ForecastResult>(
      `/api/forecasts/results/${encodeURIComponent(view.result)}`,
      { signal: controller.signal },
    )
      .then((data) => {
        setDetail(data);
        setLoading(false);
        const rawPredictions = asRows(data.predictions).concat(
          asRows(data.forecast),
        );
        const rawMetrics = asRows(data.metrics).concat(
          asRows(data.backtest?.metrics),
        );
        const backtestPredictions = asRows(data.backtest?.predictions);
        const availableModels = [
          ...new Set(
            rawPredictions
              .concat(rawMetrics, backtestPredictions)
              .map(modelKey),
          ),
        ].filter(Boolean);
        const availableAreas = [...new Set(rawPredictions.map(areaKey))].filter(
          Boolean,
        );
        const dates = rawPredictions.map(targetTime).filter(Boolean).sort();
        const origins = rawPredictions.map(originKey).filter(Boolean).sort();
        const splits = [
          ...new Set(
            rawPredictions
              .concat(rawMetrics)
              .map(explicitSplit)
              .filter(Boolean),
          ),
        ];
        const selectedSummary = results.find((item) => item.id === data.id);
        updateView(
          {
            area: availableAreas.includes(view.area)
              ? view.area
              : availableAreas[0] || selectedSummary?.areas[0] || view.area,
            start:
              view.start ||
              dates[0]?.slice(0, 10) ||
              selectedSummary?.start?.slice(0, 10) ||
              "",
            end:
              view.end ||
              dates.at(-1)?.slice(0, 10) ||
              selectedSummary?.end?.slice(0, 10) ||
              "",
            models: view.models.length
              ? view.models.filter((model) => availableModels.includes(model))
              : availableModels,
            split: splits.includes(view.split)
              ? view.split
              : splits[0] || view.split,
            origin: origins.includes(view.origin)
              ? view.origin
              : origins.at(-1) || "",
          },
          true,
        );
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") {
          setError(reason.message);
          setLoading(false);
        }
      });
    return () => controller.abort();
    // Result is the only fetch key; filters are client-side.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view?.result, results]);

  const selectedJob = jobs.find((job) => job.id === view?.job) || null;
  useEffect(() => {
    if (!selectedJob || !["queued", "running"].includes(selectedJob.status))
      return;
    const timer = window.setInterval(() => {
      apiJson<Job>(`/api/forecasts/jobs/${encodeURIComponent(selectedJob.id)}`)
        .then(async (job) => {
          setJobs((current) => [
            job,
            ...current.filter((item) => item.id !== job.id),
          ]);
          if (job.status === "succeeded" && job.resultId) {
            await loadLists();
            updateView(
              {
                result: job.resultId,
                start: "",
                end: "",
                models: [],
                origin: "",
              },
              true,
            );
          }
        })
        .catch((reason: Error) => setJobError(reason.message));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [selectedJob, loadLists, updateView]);

  const summary = results.find((item) => item.id === view?.result) || null;
  const predictionRows = useMemo<Json[]>(() => {
    if (!detail) return [];
    const direct = asRows(detail.predictions);
    if (direct.length) return direct;
    return asRows(detail.forecast).map((row) => ({
      ...row,
      model: modelKey(row),
    }));
  }, [detail]);
  const metricRows = useMemo(() => {
    if (!detail) return [];
    const direct = asRows(detail.metrics);
    return direct.length ? direct : asRows(detail.backtest?.metrics);
  }, [detail]);
  const failures = useMemo(
    () =>
      detail
        ? asRows(detail.failures).concat(asRows(detail.backtest?.failures))
        : [],
    [detail],
  );
  const trainingRows = useMemo(
    () => (detail ? asRows(detail.training) : []),
    [detail],
  );
  const backtestRows = useMemo(
    () => (detail ? asRows(detail.backtest?.predictions) : []),
    [detail],
  );
  const availableModels = useMemo(
    () =>
      [
        ...new Set(
          predictionRows
            .concat(metricRows)
            .map(modelKey)
            .concat((summary?.models || []).map(normalizeModel)),
        ),
      ].filter(Boolean),
    [predictionRows, metricRows, summary],
  );
  const availableAreas = useMemo(
    () =>
      [
        ...new Set(predictionRows.map(areaKey).concat(summary?.areas || [])),
      ].filter(Boolean),
    [predictionRows, summary],
  );
  const availableSplits = useMemo(
    () =>
      [...new Set(metricRows.concat(predictionRows).map(explicitSplit))].filter(
        Boolean,
      ),
    [metricRows, predictionRows],
  );
  const availableOrigins = useMemo(
    () =>
      [
        ...new Set(
          predictionRows
            .filter((row) => !areaKey(row) || areaKey(row) === view?.area)
            .map(originKey),
        ),
      ]
        .filter(Boolean)
        .sort(),
    [predictionRows, view?.area],
  );

  const filteredPredictions = useMemo(() => {
    if (!view) return [];
    return predictionRows.filter((row) => {
      const date = targetTime(row).slice(0, 10);
      return (
        (!areaKey(row) || areaKey(row) === view.area) &&
        (!view.start || !date || date >= view.start) &&
        (!view.end || !date || date <= view.end) &&
        view.models.includes(modelKey(row)) &&
        (!availableSplits.includes(view.split) ||
          splitKey(row) === view.split) &&
        (!view.origin ||
          !availableOrigins.length ||
          originKey(row) ===
            (availableOrigins.includes(view.origin)
              ? view.origin
              : availableOrigins.at(-1)))
      );
    });
  }, [predictionRows, view, availableSplits, availableOrigins]);

  const filteredMetrics = useMemo(() => {
    if (!view) return [];
    return metricRows.filter((row) => {
      const scope =
        textValue(row, "scope", "dimension", "breakdown") || "overall";
      const rowArea = textValue(row, "area", "priceArea");
      const rowSplit = explicitSplit(row);
      const scopeMatches =
        view.dimension === "overall"
          ? scope === "overall"
          : scope ===
              (view.dimension === "isPeakPeriod"
                ? "peak_period"
                : view.dimension) || row[view.dimension] != null;
      return (
        (!availableSplits.includes(view.split) ||
          !rowSplit ||
          rowSplit === view.split) &&
        view.models.includes(modelKey(row)) &&
        scopeMatches &&
        (view.dimension === "area" || !rowArea || rowArea === view.area)
      );
    });
  }, [metricRows, view, availableSplits]);

  const chartOption = useMemo<EChartsCoreOption>(() => {
    const rows = [...filteredPredictions].sort((a, b) =>
      targetTime(a).localeCompare(targetTime(b)),
    );
    const times = [...new Set(rows.map(targetTime).filter(Boolean))];
    const byModel = new Map<string, Map<string, Json>>();
    for (const row of rows) {
      const model = modelKey(row);
      if (!byModel.has(model)) byModel.set(model, new Map());
      byModel.get(model)!.set(targetTime(row), row);
    }
    const firstByTime = new Map<string, Json>();
    for (const row of rows)
      if (!firstByTime.has(targetTime(row)))
        firstByTime.set(targetTime(row), row);
    const intervalModel =
      [...byModel.keys()].find(
        (model) => model !== "baseline" && model !== "seasonal_naive",
      ) || [...byModel.keys()][0];
    const intervalRows = intervalModel
      ? byModel.get(intervalModel)!
      : new Map<string, Json>();
    const lower = times.map((time) =>
      numericValue(intervalRows.get(time) || {}, "lower", "q10", "lowerBound"),
    );
    const range = times.map((time, index) => {
      const upper = numericValue(
        intervalRows.get(time) || {},
        "upper",
        "q90",
        "upperBound",
      );
      return upper == null || lower[index] == null
        ? null
        : upper - lower[index]!;
    });
    const series: Json[] = [];
    if (lower.some((value) => value != null)) {
      series.push(
        {
          name: "Interval lower",
          type: "line",
          data: lower,
          stack: "interval",
          stackStrategy: "all",
          symbol: "none",
          silent: true,
          lineStyle: { opacity: 0 },
          areaStyle: { opacity: 0 },
          tooltip: { show: false },
        },
        {
          name: `${modelLabel(intervalModel || "model")} interval`,
          type: "line",
          data: range,
          stack: "interval",
          stackStrategy: "all",
          symbol: "none",
          lineStyle: { opacity: 0 },
          areaStyle: { color: "rgba(23,107,89,.20)" },
        },
      );
    }
    const actual = times.map((time) =>
      numericValue(firstByTime.get(time) || {}, "actual", "observed"),
    );
    if (actual.some((value) => value != null))
      series.push({
        name: "Actual",
        type: "line",
        data: actual,
        symbol: "none",
        lineStyle: { color: "#263a32", width: 2 },
      });
    const baseline = times.map((time) =>
      numericValue(firstByTime.get(time) || {}, "baseline", "seasonalNaive"),
    );
    if (baseline.some((value) => value != null))
      series.push({
        name: "Seasonal baseline",
        type: "line",
        data: baseline,
        symbol: "none",
        lineStyle: { color: "#9a816a", width: 1.5, type: "dashed" },
      });
    [...byModel.entries()].forEach(([model, values], index) => {
      if (["baseline", "seasonal_naive"].includes(model.toLowerCase())) return;
      series.push({
        name: modelLabel(model),
        type: "line",
        data: times.map((time) =>
          numericValue(
            values.get(time) || {},
            "prediction",
            "median",
            "forecast",
          ),
        ),
        symbol: times.length < 80 ? "circle" : "none",
        symbolSize: 4,
        lineStyle: {
          color: seriesColours[index % seriesColours.length],
          width: 2,
        },
        itemStyle: { color: seriesColours[index % seriesColours.length] },
      });
    });
    return {
      tooltip: {
        trigger: "axis",
        valueFormatter: (value: unknown) =>
          `${number(typeof value === "number" ? value : null, 1)} kWh`,
      },
      legend: {
        type: "scroll",
        top: 0,
        data: series
          .map((item) => String(item.name))
          .filter((name) => name !== "Interval lower"),
        textStyle: { color: "#52645c" },
      },
      grid: { left: 68, right: 24, top: 54, bottom: 74 },
      xAxis: {
        type: "category",
        data: times,
        axisLabel: {
          color: "#607069",
          hideOverlap: true,
          formatter: shortUtcTick,
        },
        name: "Target time (UTC)",
        nameLocation: "middle",
        nameGap: 52,
      },
      yAxis: {
        type: "value",
        name: "kWh",
        scale: true,
        axisLabel: { color: "#607069" },
        splitLine: { lineStyle: { color: "#e4e9e2" } },
      },
      dataZoom:
        times.length > 48
          ? [{ type: "inside" }, { type: "slider", bottom: 18, height: 18 }]
          : [],
      series,
    };
  }, [filteredPredictions]);

  const metricSummary = useMemo(() => {
    const models = new Set(filteredMetrics.map(modelKey));
    const values = filteredMetrics
      .flatMap((row) => [
        numericValue(row, "mae", "MAE"),
        numericValue(row, "rmse", "RMSE"),
        numericValue(row, "coverage", "intervalCoverage"),
        numericValue(row, "pinball", "pinballLoss"),
      ])
      .filter((value): value is number => value != null);
    return {
      rows: filteredMetrics.length,
      models: models.size,
      values: values.length,
    };
  }, [filteredMetrics]);

  const trainingOption = useMemo<EChartsCoreOption>(
    () => ({
      tooltip: {
        trigger: "axis",
        valueFormatter: (value: unknown) =>
          `${number(typeof value === "number" ? value : null, 1)} kWh`,
      },
      legend: { top: 0, textStyle: { color: "#52645c" } },
      grid: { left: 68, right: 24, top: 48, bottom: 70 },
      xAxis: {
        type: "category",
        data: trainingRows.map(targetTime),
        axisLabel: {
          color: "#607069",
          hideOverlap: true,
          formatter: shortUtcTick,
        },
        name: "Training time (UTC)",
        nameLocation: "middle",
        nameGap: 50,
      },
      yAxis: {
        type: "value",
        name: "kWh",
        scale: true,
        axisLabel: { color: "#607069" },
        splitLine: { lineStyle: { color: "#e4e9e2" } },
      },
      dataZoom:
        trainingRows.length > 100
          ? [{ type: "inside" }, { type: "slider", bottom: 17, height: 18 }]
          : [],
      series: [
        {
          name: "Actual",
          type: "line",
          data: trainingRows.map((row) => numericValue(row, "actual")),
          symbol: "none",
          lineStyle: { color: "#263a32", width: 1.5 },
        },
        {
          name: "One-step fitted",
          type: "line",
          data: trainingRows.map((row) => numericValue(row, "fitted")),
          symbol: "none",
          lineStyle: { color: "#3f7eaa", width: 1 },
        },
        {
          name: "Dynamic fitted",
          type: "line",
          data: trainingRows.map((row) => numericValue(row, "dynamic")),
          symbol: "none",
          lineStyle: { color: "#d4774d", width: 1.5, type: "dashed" },
        },
      ],
    }),
    [trainingRows],
  );

  const backtestOption = useMemo<EChartsCoreOption>(() => {
    const latestOrigin =
      [...new Set(backtestRows.map(originKey).filter(Boolean))].sort().at(-1) ||
      "";
    const rows = backtestRows
      .filter((row) => !latestOrigin || originKey(row) === latestOrigin)
      .sort((a, b) => targetTime(a).localeCompare(targetTime(b)));
    const times = [...new Set(rows.map(targetTime))];
    const byModel = new Map<string, Map<string, Json>>();
    for (const row of rows) {
      const key = modelKey(row);
      if (!byModel.has(key)) byModel.set(key, new Map());
      byModel.get(key)!.set(targetTime(row), row);
    }
    const first = new Map<string, Json>();
    rows.forEach((row) => {
      if (!first.has(targetTime(row))) first.set(targetTime(row), row);
    });
    return {
      tooltip: {
        trigger: "axis",
        valueFormatter: (value: unknown) =>
          `${number(typeof value === "number" ? value : null, 1)} kWh`,
      },
      legend: { top: 0, textStyle: { color: "#52645c" } },
      grid: { left: 68, right: 24, top: 48, bottom: 58 },
      xAxis: {
        type: "category",
        data: times,
        axisLabel: {
          color: "#607069",
          hideOverlap: true,
          formatter: shortUtcTick,
        },
        name: "Target time (UTC)",
        nameLocation: "middle",
        nameGap: 44,
      },
      yAxis: {
        type: "value",
        name: "kWh",
        scale: true,
        axisLabel: { color: "#607069" },
        splitLine: { lineStyle: { color: "#e4e9e2" } },
      },
      series: [
        {
          name: "Actual",
          type: "line",
          data: times.map((time) =>
            numericValue(first.get(time) || {}, "actual"),
          ),
          symbol: "none",
          lineStyle: { color: "#263a32", width: 2 },
        },
        ...[...byModel.entries()].map(([model, values], index) => ({
          name: modelLabel(model),
          type: "line",
          data: times.map((time) =>
            numericValue(values.get(time) || {}, "prediction"),
          ),
          symbol: "circle",
          symbolSize: 4,
          lineStyle: {
            color: seriesColours[index % seriesColours.length],
            width: 1.7,
            type: model.toLowerCase().includes("naive") ? "dashed" : "solid",
          },
        })),
      ],
    };
  }, [backtestRows]);

  async function submitJob(kind: Job["kind"], config: Json) {
    setRunningAction(true);
    setJobError("");
    try {
      const job = await apiJson<Job>("/api/forecasts/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, config }),
      });
      setJobs((current) => [
        job,
        ...current.filter((item) => item.id !== job.id),
      ]);
      updateView({ job: job.id });
    } catch (reason) {
      setJobError(
        reason instanceof Error
          ? reason.message
          : "The job could not be started.",
      );
    } finally {
      setRunningAction(false);
    }
  }

  function runEvaluation(event: FormEvent) {
    event.preventDefault();
    const origins = (value: string) =>
      value
        .split(",")
        .map((item) => `${item.trim()}T00:00:00Z`)
        .filter((item) => /^\d{4}-\d{2}-\d{2}T/.test(item));
    submitJob("evaluation", {
      areas: evaluation.areas,
      models: evaluation.models,
      horizon_hours: evaluation.horizon,
      train_window_days: evaluation.trainDays,
      validation_origins: origins(evaluation.validationOrigins),
      calibration_origins: origins(evaluation.calibrationOrigins),
      holdout_origins: origins(evaluation.holdoutOrigins),
      weather_mode: evaluation.weatherMode,
      energy_publication_lag_hours: evaluation.energyLag,
      weather_publication_lag_hours: evaluation.weatherLag,
      interval_coverage: evaluation.coverage,
      random_seed: evaluation.randomSeed,
    });
  }

  function runSarimax(event: FormEvent) {
    event.preventDefault();
    const days =
      (Date.parse(sarimax.end) - Date.parse(sarimax.start)) / 86_400_000;
    if (!Number.isFinite(days) || days < 2 || days > 366) {
      setJobError(
        "Training start must precede end by at least 2 days, and the API-exclusive interval is limited to 366 days.",
      );
      return;
    }
    submitJob("sarimax", {
      area: sarimax.area,
      kind: sarimax.kind,
      group: sarimax.group,
      start: sarimax.start,
      end: sarimax.end,
      frequency: sarimax.frequency,
      horizon: sarimax.horizon,
      order: sarimax.order,
      seasonalOrder: sarimax.seasonal ? sarimax.seasonalOrder : [0, 0, 0, 0],
      weatherVariables: sarimax.weatherVariables,
      futureWeather: sarimax.futureWeather,
      dynamic: sarimax.dynamic,
      dynamicStart: sarimax.dynamicStart,
      backtest: sarimax.backtest,
      baselineLag: sarimax.baselineLag,
      backtestHorizon: sarimax.backtestHorizon,
      step: sarimax.step,
      folds: sarimax.folds,
      evalNoExog: sarimax.weatherVariables.length ? sarimax.evalNoExog : false,
      energyLagHours: sarimax.energyLagHours,
      weatherLagHours: sarimax.weatherLagHours,
    });
  }

  async function cancelJob() {
    if (!selectedJob) return;
    setRunningAction(true);
    setJobError("");
    try {
      const job = await apiJson<Job>(
        `/api/forecasts/jobs/${encodeURIComponent(selectedJob.id)}/cancel`,
        { method: "POST" },
      );
      setJobs((current) => [
        job,
        ...current.filter((item) => item.id !== job.id),
      ]);
    } catch (reason) {
      setJobError(
        reason instanceof Error
          ? reason.message
          : "The job could not be cancelled.",
      );
    } finally {
      setRunningAction(false);
    }
  }

  if (!view) {
    return (
      <AnalysisShell
        title="Forecasts & evaluation"
        description="Loading forecast controls…"
      >
        <p role="status">Loading…</p>
      </AnalysisShell>
    );
  }

  const metadata = detail?.metadata || summary?.metadata || {};
  const originsMetadata = asObject(detail?.origins);
  const holdoutOrigins = Array.isArray(originsMetadata.holdout)
    ? originsMetadata.holdout
    : [];
  const selectedOrigin =
    detail?.kind === "evaluation"
      ? availableOrigins.includes(view.origin)
        ? view.origin
        : availableOrigins.at(-1) || ""
      : "";
  const eligibleCutoff = (lag: unknown) =>
    selectedOrigin && typeof lag === "number"
      ? new Date(
          new Date(selectedOrigin).valueOf() - (lag + 1) * 3600000,
        ).toISOString()
      : null;
  const issueTime =
    selectedOrigin ||
    summary?.issueTime ||
    nestedValue(metadata, ["issueTime", "issue_time"]) ||
    (holdoutOrigins.length
      ? `${holdoutOrigins.length} saved holdout origins`
      : null);
  const lastEnergy =
    eligibleCutoff(detail?.config?.energy_publication_lag_hours) ||
    nestedValue(metadata, [
      "lastAvailableEnergy",
      "last_available_energy",
      "availability.lastEnergy",
      "availability.energy",
      "assumptions.energyAvailability",
    ]);
  const lastWeather =
    (detail?.config?.weather_mode === "realized_future_upper_bound"
      ? "Realized target weather (upper bound)"
      : eligibleCutoff(detail?.config?.weather_publication_lag_hours)) ||
    nestedValue(metadata, [
      "lastAvailableWeather",
      "last_available_weather",
      "availability.lastWeather",
      "availability.weather",
      "assumptions.weatherAvailability",
    ]);
  const source =
    summary?.sourceLabel ||
    nestedValue(metadata, ["sourceLabel", "source", "dataset.source"]);
  const weatherMode =
    summary?.weatherMode ||
    nestedValue(metadata, ["weatherMode", "weather_mode"]);
  const upperBound =
    String(weatherMode).includes("upper_bound") ||
    String(weatherMode).includes("realized");
  const configuredWeather =
    detail?.kind === "sarimax" && Array.isArray(detail.config?.weatherVariables)
      ? detail.config.weatherVariables
      : null;

  return (
    <AnalysisShell
      title="Forecasts & evaluation"
      description="Can we predict tomorrow’s electricity use? Compare saved forecasts with actual outcomes, then explore the evidence behind each model."
    >
      <section
        className={styles.selectorPanel}
        aria-labelledby="prepared-title"
      >
        <div>
          <span className={styles.sectionKicker}>Prepared results</span>
          <h2 id="prepared-title">Forecast results</h2>
          <p>
            Review the selected task across its saved dates, price areas, models
            and matched forecast origins.
          </p>
        </div>
        <div className={styles.selectorGrid}>
          <label>
            Result
            <select
              value={view.result}
              onChange={(event) =>
                updateView({
                  result: event.target.value,
                  start: "",
                  end: "",
                  models: [],
                  origin: "",
                })
              }
            >
              {results.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.title} · {item.kind}
                </option>
              ))}
            </select>
          </label>
          <label>
            Job
            <select
              value={view.job}
              onChange={(event) => updateView({ job: event.target.value })}
            >
              <option value="">No job selected</option>
              {jobs.map((job) => (
                <option value={job.id} key={job.id}>
                  {job.kind} · {job.status} · {formatDateTime(job.createdAt)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      {selectedJob && (
        <section className="analysis-panel" aria-label="Selected forecast job">
          <ResultStatus job={selectedJob} />
          <div className="analysis-actions">
            {["queued", "running"].includes(selectedJob.status) && (
              <button
                type="button"
                onClick={cancelJob}
                disabled={runningAction}
              >
                <Square size={14} aria-hidden="true" /> Cancel job
              </button>
            )}
            {selectedJob.resultId && (
              <button
                type="button"
                onClick={() =>
                  updateView({
                    result: selectedJob.resultId!,
                    start: "",
                    end: "",
                    models: [],
                    origin: "",
                  })
                }
              >
                Open result
              </button>
            )}
          </div>
          {selectedJob.error && (
            <p className={styles.error} role="alert">
              {selectedJob.error}
            </p>
          )}
          <details>
            <summary>Submitted configuration and enforced limits</summary>
            <pre>
              {JSON.stringify(
                { config: selectedJob.config, limits: selectedJob.limits },
                null,
                2,
              )}
            </pre>
          </details>
        </section>
      )}
      {jobError && (
        <p className={styles.error} role="alert">
          {jobError}
        </p>
      )}

      {error && (
        <section className="analysis-panel">
          <p className={styles.error} role="alert">
            {error}
          </p>
        </section>
      )}
      {loading && (
        <p role="status" className={styles.loading}>
          Loading stored forecast result…
        </p>
      )}
      {!loading && !error && !detail && (
        <section className="analysis-panel">
          <h2>No prepared result is available</h2>
          <p>
            Start a bounded evaluation or SARIMAX job below. Completed jobs
            create immutable results that can be revisited from this selector.
          </p>
        </section>
      )}

      {detail && (
        <>
          <section
            className={styles.evidenceStrip}
            aria-label="Forecast evidence context"
          >
            <div>
              <Database size={17} aria-hidden="true" />
              <span>Source</span>
              <strong>{String(source || "Stored versioned artifact")}</strong>
            </div>
            <div>
              <Clock3 size={17} aria-hidden="true" />
              <span>Forecast issue</span>
              <strong>{formatDateTime(issueTime)}</strong>
            </div>
            <div>
              <span>
                {detail.kind === "evaluation"
                  ? "Energy eligibility cutoff"
                  : "Last energy available"}
              </span>
              <strong>{formatDateTime(lastEnergy)}</strong>
            </div>
            <div>
              <span>
                {detail.kind === "evaluation"
                  ? "Weather eligibility cutoff"
                  : "Last weather available"}
              </span>
              <strong>
                {configuredWeather?.length === 0
                  ? "Not used"
                  : formatDateTime(lastWeather)}
              </strong>
            </div>
          </section>
          <p
            className={upperBound ? styles.upperBound : styles.retrospective}
            role="note"
          >
            {upperBound
              ? "Realized future weather upper bound: this retrospective experiment uses weather that was not available at issue time. It is not an operational forecast."
              : detail.kind === "sarimax"
                ? "Retrospective custom experiment using revised snapshots and assumed publication lags. Its projected weather scenario and historical fit are not an as-issued operational forecast."
                : "Retrospective held-out evaluation: publication lags and historical availability are applied. Historical performance does not promise operational accuracy."}
          </p>
          {detail.kind === "sarimax" && detail.converged === false && (
            <p className={styles.error} role="alert">
              The optimizer did not converge. Forecasts and nominal intervals
              may be unreliable; reduce the orders or disable seasonality before
              drawing conclusions.
            </p>
          )}
          {detail.kind === "sarimax" &&
            Array.isArray(detail.warnings) &&
            detail.warnings.length > 0 && (
              <details className={styles.failures}>
                <summary>
                  {detail.warnings.length} model warning
                  {detail.warnings.length === 1 ? "" : "s"}
                </summary>
                <pre>{detail.warnings.map(String).join("\n")}</pre>
              </details>
            )}

          <form
            className="analysis-controls"
            onSubmit={(event) => event.preventDefault()}
            aria-label="Stored result filters"
          >
            <label>
              Area
              <select
                value={view.area}
                onChange={(event) => updateView({ area: event.target.value })}
              >
                {availableAreas.map((area) => (
                  <option key={area}>{area}</option>
                ))}
              </select>
            </label>
            <label>
              Start target date (UTC)
              <input
                type="date"
                value={view.start}
                onChange={(event) => updateView({ start: event.target.value })}
              />
            </label>
            <label>
              End target date (UTC)
              <input
                type="date"
                value={view.end}
                onChange={(event) => updateView({ end: event.target.value })}
              />
            </label>
            {availableSplits.length > 0 && (
              <label>
                Evaluation cohort
                <select
                  value={
                    availableSplits.includes(view.split)
                      ? view.split
                      : availableSplits[0]
                  }
                  onChange={(event) =>
                    updateView({ split: event.target.value })
                  }
                >
                  {availableSplits.map((split) => (
                    <option key={split} value={split}>
                      {split === "matched_holdout" || split === "holdout"
                        ? "Matched final holdout (untouched)"
                        : split === "validation"
                          ? "Validation / tuning"
                          : split.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {availableOrigins.length > 0 && (
              <label>
                Matched forecast origin
                <select
                  value={
                    availableOrigins.includes(view.origin)
                      ? view.origin
                      : availableOrigins.at(-1)
                  }
                  onChange={(event) =>
                    updateView({ origin: event.target.value })
                  }
                >
                  {availableOrigins.map((origin) => (
                    <option key={origin} value={origin}>
                      {formatDateTime(origin)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label>
              Metric breakdown
              <select
                value={view.dimension}
                onChange={(event) =>
                  updateView({ dimension: event.target.value })
                }
              >
                <option value="overall">Overall</option>
                <option value="area">Area</option>
                <option value="season">Season</option>
                <option value="horizon">Horizon</option>
                <option value="isPeakPeriod">Peak period</option>
              </select>
            </label>
            <fieldset className={styles.inlineChecks}>
              <legend>Models</legend>
              {availableModels.map((model) => (
                <label key={model}>
                  <input
                    type="checkbox"
                    checked={view.models.includes(model)}
                    onChange={(event) =>
                      updateView({
                        models: event.target.checked
                          ? [...view.models, model]
                          : view.models.filter((item) => item !== model),
                      })
                    }
                  />{" "}
                  {modelLabel(model)}
                </label>
              ))}
            </fieldset>
          </form>

          <section className="analysis-panel">
            <div className={styles.panelHeading}>
              <div>
                <span className={styles.sectionKicker}>
                  {detail.kind === "sarimax"
                    ? "Issued custom forecast"
                    : "Matched-origin forecast"}
                </span>
                <h2>
                  {detail.kind === "sarimax"
                    ? "Forecast, seasonal baseline and uncertainty"
                    : "Actual demand, baseline and model estimates"}
                </h2>
              </div>
              <span>
                {view.area} · {summary?.horizon || 24} steps
              </span>
            </div>
            <p>
              {detail.kind === "sarimax"
                ? "Future actuals are not available in this issued forecast; use its rolling backtest below for an actual comparison. "
                : ""}
              The shaded band is the selected model&apos;s stored predictive
              interval. It represents conditional model uncertainty; weather
              uncertainty is included only when the artifact metadata says so.
            </p>
            {filteredPredictions.length ? (
              <AnalysisChart
                option={chartOption}
                label={`${detail.title} ${view.area} ${view.split} forecast`}
                height={440}
              />
            ) : (
              <p className={styles.empty}>
                No forecast rows match these filters.
              </p>
            )}
            <div className="analysis-actions">
              <button
                type="button"
                disabled={!filteredPredictions.length}
                onClick={() =>
                  downloadCsv(
                    `forecast-${detail.id}-${view.area}-${view.split}.csv`,
                    csvRows(filteredPredictions),
                  )
                }
              >
                Download displayed CSV
              </button>
              <button
                type="button"
                onClick={() =>
                  downloadJson(`forecast-${detail.id}-metadata.json`, {
                    id: detail.id,
                    title: detail.title,
                    kind: detail.kind,
                    createdAt: detail.createdAt,
                    config: detail.config,
                    selectedParameters: detail.selectedParameters,
                    calibration: detail.calibration,
                    origins: detail.origins,
                    coverage: detail.coverage,
                    failures: detail.failures || detail.backtest?.failures,
                    metadata,
                    filters: view,
                  })
                }
              >
                Download metadata JSON
              </button>
            </div>
          </section>

          {detail.kind === "sarimax" && trainingRows.length > 0 && (
            <section className="analysis-panel">
              <div className={styles.panelHeading}>
                <div>
                  <span className={styles.sectionKicker}>
                    In-sample diagnostics
                  </span>
                  <h2>Actual, fitted and dynamic training path</h2>
                </div>
                <span>{number(numericValue(detail, "aic"), 1)} AIC</span>
              </div>
              <p>
                One-step fitted values use preceding actuals. After the
                configured dynamic start, the dynamic path recursively uses
                prior predictions. Both are descriptive in-sample diagnostics.
              </p>
              <AnalysisChart
                option={trainingOption}
                label={`${detail.title} in-sample actual fitted dynamic`}
                height={350}
              />
            </section>
          )}

          {detail.kind === "sarimax" && backtestRows.length > 0 && (
            <section className="analysis-panel">
              <div className={styles.panelHeading}>
                <div>
                  <span className={styles.sectionKicker}>
                    Rolling-origin development check
                  </span>
                  <h2>Latest matched backtest origin</h2>
                </div>
                <span>{detail.backtest?.metrics?.length || 0} models</span>
              </div>
              <p>
                This custom backtest is a development-period diagnostic, not the
                untouched benchmark holdout. Every displayed model uses the same
                latest origin and target hours.
              </p>
              <AnalysisChart
                option={backtestOption}
                label={`${detail.title} latest rolling backtest`}
                height={350}
              />
            </section>
          )}

          <section className="analysis-panel">
            <div className={styles.panelHeading}>
              <div>
                <span className={styles.sectionKicker}>
                  {detail.kind === "sarimax"
                    ? "Rolling-origin development metrics"
                    : ["holdout", "matched_holdout"].includes(view.split)
                      ? "Untouched final holdout"
                      : "Model development split"}
                </span>
                <h2>Accuracy and interval quality</h2>
                {detail.kind === "evaluation" && (
                  <p>
                    Metrics cover all saved matched holdout origins and areas.
                    Area, date and origin filters above apply to the forecast
                    chart; use the Area breakdown for regional scores.
                  </p>
                )}
              </div>
              <span>
                {metricSummary.rows} metric rows · {metricSummary.models} models
              </span>
            </div>
            <p>
              MAE and RMSE use kWh. Coverage is the share of actuals inside the
              interval; width measures sharpness at that coverage, and pinball
              loss evaluates quantiles. MASE scales error by in-sample seasonal
              change. MASE below 1 does not by itself prove a model beat the
              displayed held-out baseline; compare their errors on the same
              targets directly.
            </p>
            <MetricTable rows={filteredMetrics} dimension={view.dimension} />
            <div className="analysis-actions">
              <button
                type="button"
                disabled={!filteredMetrics.length}
                onClick={() =>
                  downloadCsv(
                    `metrics-${detail.id}-${view.split}-${view.dimension}.csv`,
                    csvRows(filteredMetrics),
                  )
                }
              >
                Download displayed metrics CSV
              </button>
            </div>
            {failures.length > 0 && (
              <details className={styles.failures}>
                <summary>
                  {failures.length} recorded fold failure
                  {failures.length === 1 ? "" : "s"}
                </summary>
                <p>
                  Failures remain visible and are not silently removed from
                  model comparisons.
                </p>
                <pre>{JSON.stringify(failures, null, 2)}</pre>
              </details>
            )}
          </section>

          <section className="analysis-panel">
            <h2>Methods, sources and limitations</h2>
            <p>
              Prepared household-demand benchmarks use all five price areas, a
              24-hour target, baseline, Ridge, gradient boosting and SARIMAX on
              matched origins. Validation supports tuning; the final holdout
              remains separate. Features and lags are defined relative to the
              saved issue time and last available observations.
            </p>
            <details>
              <summary>Artifact metadata</summary>
              <pre>
                {JSON.stringify({ metadata, config: detail.config }, null, 2)}
              </pre>
            </details>
          </section>
        </>
      )}

      {customJobsEnabled ? (
        <section
          className={styles.jobsSection}
          aria-labelledby="experiments-title"
        >
          <span className={styles.sectionKicker}>Bounded compute</span>
          <h2 id="experiments-title">Run an experiment</h2>
          <p>
            Compare a prepared set of areas and models, or configure a focused
            SARIMAX forecast. Submitted runs report progress and can be
            cancelled.
          </p>
          <div className="analysis-grid">
            <EvaluationForm
              value={evaluation}
              onChange={setEvaluation}
              onSubmit={runEvaluation}
              disabled={runningAction}
            />
            <SarimaxForm
              value={sarimax}
              onChange={setSarimax}
              onSubmit={runSarimax}
              disabled={runningAction}
            />
          </div>
        </section>
      ) : (
        <section className="analysis-panel">
          <h2>Prepared results</h2>
          <p>
            Custom runs are disabled on this deployment. You can explore and
            download the saved results above. Run your own experiments with the
            local installation.
          </p>
        </section>
      )}
    </AnalysisShell>
  );
}

function MetricTable({ rows, dimension }: { rows: Json[]; dimension: string }) {
  if (!rows.length)
    return (
      <p className={styles.empty}>
        No metric rows match this split, model and breakdown.
      </p>
    );
  return (
    <div className={styles.tableWrap}>
      <table>
        <thead>
          <tr>
            <th>Model</th>
            {dimension !== "overall" && (
              <th>{dimension === "isPeakPeriod" ? "Period" : dimension}</th>
            )}
            <th>MAE</th>
            <th>RMSE</th>
            <th>MASE</th>
            <th>Baseline MAE</th>
            <th>Coverage</th>
            <th>Mean width</th>
            <th>Pinball lower</th>
            <th>Pinball median</th>
            <th>Pinball upper</th>
            <th>n</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const rawDimension = row[dimension];
            const dimensionValue =
              typeof rawDimension === "boolean"
                ? rawDimension
                  ? "Peak"
                  : "Off-peak"
                : textValue(row, dimension, "bucket", "label") ||
                  numericValue(row, dimension)?.toString() ||
                  "All";
            const coverage = numericValue(row, "coverage", "intervalCoverage");
            const legacyPinball = numericValue(row, "pinball", "pinballLoss");
            return (
              <tr key={`${modelKey(row)}-${dimensionValue}-${index}`}>
                <th>{modelLabel(modelKey(row))}</th>
                {dimension !== "overall" && <td>{dimensionValue}</td>}
                <td>{number(numericValue(row, "mae", "MAE"), 2)}</td>
                <td>{number(numericValue(row, "rmse", "RMSE"), 2)}</td>
                <td>{number(numericValue(row, "mase", "MASE"), 3)}</td>
                <td>
                  {number(numericValue(row, "baselineMae", "baseline_mae"), 2)}
                </td>
                <td>
                  {coverage == null
                    ? "—"
                    : `${number(coverage * (coverage <= 1 ? 100 : 1), 1)}%`}
                </td>
                <td>
                  {number(
                    numericValue(
                      row,
                      "width",
                      "meanWidth",
                      "intervalWidth",
                      "meanIntervalWidth",
                    ),
                    2,
                  )}
                </td>
                <td>
                  {number(
                    numericValue(row, "pinballLower") ?? legacyPinball,
                    3,
                  )}
                </td>
                <td>
                  {number(
                    numericValue(row, "pinballMedian") ?? legacyPinball,
                    3,
                  )}
                </td>
                <td>
                  {number(
                    numericValue(row, "pinballUpper") ?? legacyPinball,
                    3,
                  )}
                </td>
                <td>
                  {number(
                    numericValue(row, "n", "count", "observations", "points"),
                    0,
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function EvaluationForm({
  value,
  onChange,
  onSubmit,
  disabled,
}: {
  value: EvaluationDraft;
  onChange: (value: EvaluationDraft) => void;
  onSubmit: (event: FormEvent) => void;
  disabled: boolean;
}) {
  return (
    <form className={styles.jobForm} onSubmit={onSubmit}>
      <div className={styles.formTitle}>
        <div>
          <h3>Household-demand evaluation</h3>
          <p>Matched origins across areas and models.</p>
        </div>
        <span>24 h default</span>
      </div>
      <fieldset>
        <legend>Price areas</legend>
        <div className={styles.checkGrid}>
          {Object.keys(areas).map((area) => (
            <label key={area}>
              <input
                type="checkbox"
                checked={value.areas.includes(area)}
                onChange={(event) =>
                  onChange({
                    ...value,
                    areas: event.target.checked
                      ? [...value.areas, area]
                      : value.areas.filter((item) => item !== area),
                  })
                }
              />{" "}
              {area}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend>Models</legend>
        <div className={styles.checkGrid}>
          {benchmarkModels.map((model) => (
            <label key={model}>
              <input
                type="checkbox"
                checked={value.models.includes(model)}
                onChange={(event) =>
                  onChange({
                    ...value,
                    models: event.target.checked
                      ? [...value.models, model]
                      : value.models.filter((item) => item !== model),
                  })
                }
              />{" "}
              {modelLabel(model)}
            </label>
          ))}
        </div>
      </fieldset>
      <div className={styles.formGrid}>
        <NumberField
          label="Horizon (hours)"
          min={1}
          max={48}
          value={value.horizon}
          onChange={(horizon) => onChange({ ...value, horizon })}
        />
        <NumberField
          label="Training window (days)"
          min={30}
          max={365}
          value={value.trainDays}
          onChange={(trainDays) => onChange({ ...value, trainDays })}
        />
        <label>
          Validation origins (UTC dates)
          <input
            type="text"
            required
            value={value.validationOrigins}
            onChange={(event) =>
              onChange({ ...value, validationOrigins: event.target.value })
            }
          />
        </label>
        <label>
          Calibration origins (UTC dates)
          <input
            type="text"
            required
            value={value.calibrationOrigins}
            onChange={(event) =>
              onChange({ ...value, calibrationOrigins: event.target.value })
            }
          />
        </label>
        <label>
          Final holdout origins (UTC dates)
          <input
            type="text"
            required
            value={value.holdoutOrigins}
            onChange={(event) =>
              onChange({ ...value, holdoutOrigins: event.target.value })
            }
          />
        </label>
        <NumberField
          label="Interval coverage"
          min={0.5}
          max={0.99}
          step={0.05}
          value={value.coverage}
          onChange={(coverage) => onChange({ ...value, coverage })}
        />
        <NumberField
          label="Energy lag (hours)"
          min={24}
          max={168}
          value={value.energyLag}
          onChange={(energyLag) => onChange({ ...value, energyLag })}
        />
        <NumberField
          label="Weather lag (hours)"
          min={24}
          max={240}
          value={value.weatherLag}
          onChange={(weatherLag) => onChange({ ...value, weatherLag })}
        />
        <NumberField
          label="Random seed"
          min={0}
          max={999999}
          value={value.randomSeed}
          onChange={(randomSeed) => onChange({ ...value, randomSeed })}
        />
        <label>
          Weather availability
          <select
            value={value.weatherMode}
            onChange={(event) =>
              onChange({
                ...value,
                weatherMode: event.target
                  .value as EvaluationDraft["weatherMode"],
              })
            }
          >
            <option value="historical_only">
              Historical data available at issue
            </option>
            <option value="realized_future_upper_bound">
              Realized future weather (upper bound)
            </option>
          </select>
        </label>
      </div>
      <p className={styles.limitNote}>
        Enter origin dates as comma-separated YYYY-MM-DD values. Every
        validation origin must precede calibration, and every calibration origin
        must precede the final holdout. Limits: 1–48 forecast hours, 30–365
        training days, energy lag 24–168 h, weather lag 24–240 h. Operational
        weather forecasts are intentionally unavailable until archived
        issue-time data exists.
      </p>
      <button
        className={styles.runButton}
        type="submit"
        disabled={disabled || !value.areas.length || !value.models.length}
      >
        <Play size={15} aria-hidden="true" /> Run evaluation job
      </button>
    </form>
  );
}

function sarimaxStateCount(value: SarimaxDraft) {
  const [p, d, q] = value.order;
  if (!value.seasonal) return Math.max(p, q + 1) + d;
  const [P, D, Q, s] = value.seasonalOrder;
  return Math.max(p + P * s, q + Q * s + 1) + d + D * s;
}

function SarimaxForm({
  value,
  onChange,
  onSubmit,
  disabled,
}: {
  value: SarimaxDraft;
  onChange: (value: SarimaxDraft) => void;
  onSubmit: (event: FormEvent) => void;
  disabled: boolean;
}) {
  const groups =
    value.kind === "production" ? productionGroups : consumptionGroups;
  const horizonMax = value.frequency === "h" ? 168 : 60;
  const sMax = value.frequency === "h" ? 168 : 60;
  const setOrder = (index: number, next: number) => {
    const order: [number, number, number] = [...value.order];
    order[index] = next;
    onChange({ ...value, order });
  };
  const setSeasonal = (index: number, next: number) => {
    const seasonalOrder: [number, number, number, number] = [
      ...value.seasonalOrder,
    ];
    seasonalOrder[index] = next;
    onChange({ ...value, seasonalOrder });
  };
  return (
    <form className={styles.jobForm} onSubmit={onSubmit}>
      <div className={styles.formTitle}>
        <div>
          <h3>Custom SARIMAX</h3>
          <p>Legacy controls with explicit availability lags.</p>
        </div>
        <span>State budget 64</span>
      </div>
      <div className={styles.formGrid}>
        <label>
          Area
          <select
            value={value.area}
            onChange={(event) =>
              onChange({ ...value, area: event.target.value })
            }
          >
            {Object.keys(areas).map((area) => (
              <option key={area}>{area}</option>
            ))}
          </select>
        </label>
        <label>
          Energy kind
          <select
            value={value.kind}
            onChange={(event) => {
              const kind = event.target.value as SarimaxDraft["kind"];
              onChange({
                ...value,
                kind,
                group: kind === "production" ? "hydro" : "household",
              });
            }}
          >
            <option value="production">Production</option>
            <option value="consumption">Consumption</option>
          </select>
        </label>
        <label>
          Group
          <select
            value={value.group}
            onChange={(event) =>
              onChange({ ...value, group: event.target.value })
            }
          >
            {groups.map((group) => (
              <option key={group}>{group}</option>
            ))}
          </select>
        </label>
        <label>
          Frequency
          <select
            value={value.frequency}
            onChange={(event) => {
              const frequency = event.target.value as SarimaxDraft["frequency"];
              onChange({
                ...value,
                frequency,
                horizon: frequency === "h" ? 24 : 30,
                baselineLag: frequency === "h" ? 168 : 7,
                backtestHorizon: frequency === "h" ? 24 : 7,
                step: frequency === "h" ? 24 : 1,
                seasonalOrder: [
                  value.seasonalOrder[0],
                  value.seasonalOrder[1],
                  value.seasonalOrder[2],
                  frequency === "h" ? 24 : 7,
                ],
              });
            }}
          >
            <option value="h">Hourly</option>
            <option value="D">Daily</option>
          </select>
        </label>
        <label>
          Training start (UTC)
          <input
            type="date"
            required
            value={value.start}
            onChange={(event) =>
              onChange({ ...value, start: event.target.value })
            }
          />
        </label>
        <label>
          Training end (UTC, exclusive)
          <input
            type="date"
            required
            value={value.end}
            onChange={(event) =>
              onChange({ ...value, end: event.target.value })
            }
          />
        </label>
        <NumberField
          label={`Horizon (${value.frequency === "h" ? "hours" : "days"})`}
          min={1}
          max={horizonMax}
          value={value.horizon}
          onChange={(horizon) => onChange({ ...value, horizon })}
        />
        <label>
          Future weather
          <select
            value={value.futureWeather}
            disabled={!value.weatherVariables.length}
            onChange={(event) =>
              onChange({
                ...value,
                futureWeather: event.target
                  .value as SarimaxDraft["futureWeather"],
              })
            }
          >
            <option value="last">Repeat last available row</option>
            <option value="hod-mean">Hour/day-of-week mean</option>
          </select>
        </label>
      </div>
      <fieldset>
        <legend>Weather regressors</legend>
        <div className={styles.checkGrid}>
          {weatherVariables.map(([key, label]) => (
            <label key={key}>
              <input
                type="checkbox"
                checked={value.weatherVariables.includes(key)}
                onChange={(event) =>
                  onChange({
                    ...value,
                    weatherVariables: event.target.checked
                      ? [...value.weatherVariables, key]
                      : value.weatherVariables.filter((item) => item !== key),
                  })
                }
              />{" "}
              {label}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend>Nonseasonal order (p, d, q)</legend>
        <div className={styles.compactGrid}>
          <NumberField
            label="p"
            min={0}
            max={3}
            value={value.order[0]}
            onChange={(next) => setOrder(0, next)}
          />
          <NumberField
            label="d"
            min={0}
            max={2}
            value={value.order[1]}
            onChange={(next) => setOrder(1, next)}
          />
          <NumberField
            label="q"
            min={0}
            max={3}
            value={value.order[2]}
            onChange={(next) => setOrder(2, next)}
          />
        </div>
      </fieldset>
      <fieldset>
        <legend>
          <label className={styles.legendCheck}>
            <input
              type="checkbox"
              checked={value.seasonal}
              onChange={(event) =>
                onChange({ ...value, seasonal: event.target.checked })
              }
            />{" "}
            Seasonal order (P, D, Q, s)
          </label>
        </legend>
        <div className={styles.compactGrid}>
          <NumberField
            label="P"
            min={0}
            max={1}
            value={value.seasonalOrder[0]}
            disabled={!value.seasonal}
            onChange={(next) => setSeasonal(0, next)}
          />
          <NumberField
            label="D"
            min={0}
            max={2}
            value={value.seasonalOrder[1]}
            disabled={!value.seasonal}
            onChange={(next) => setSeasonal(1, next)}
          />
          <NumberField
            label="Q"
            min={0}
            max={1}
            value={value.seasonalOrder[2]}
            disabled={!value.seasonal}
            onChange={(next) => setSeasonal(2, next)}
          />
          <NumberField
            label="s"
            min={2}
            max={sMax}
            value={value.seasonalOrder[3]}
            disabled={!value.seasonal}
            onChange={(next) => setSeasonal(3, next)}
          />
        </div>
      </fieldset>
      <fieldset>
        <legend>
          <label className={styles.legendCheck}>
            <input
              type="checkbox"
              checked={value.dynamic}
              onChange={(event) =>
                onChange({ ...value, dynamic: event.target.checked })
              }
            />{" "}
            Dynamic in-sample prediction
          </label>
        </legend>
        <label>
          Dynamic start: {Math.round(value.dynamicStart * 100)}%
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            disabled={!value.dynamic}
            value={value.dynamicStart}
            onChange={(event) =>
              onChange({ ...value, dynamicStart: Number(event.target.value) })
            }
          />
        </label>
      </fieldset>
      <fieldset>
        <legend>
          <label className={styles.legendCheck}>
            <input
              type="checkbox"
              checked={value.backtest}
              onChange={(event) =>
                onChange({ ...value, backtest: event.target.checked })
              }
            />{" "}
            Rolling-origin backtest
          </label>
        </legend>
        <div className={styles.compactGrid}>
          <NumberField
            label="Baseline lag"
            min={1}
            max={value.frequency === "h" ? 336 : 60}
            value={value.baselineLag}
            disabled={!value.backtest}
            onChange={(baselineLag) => onChange({ ...value, baselineLag })}
          />
          <NumberField
            label="Backtest horizon"
            min={1}
            max={horizonMax}
            value={value.backtestHorizon}
            disabled={!value.backtest}
            onChange={(backtestHorizon) =>
              onChange({ ...value, backtestHorizon })
            }
          />
          <NumberField
            label="Cutoff step"
            min={1}
            max={horizonMax}
            value={value.step}
            disabled={!value.backtest}
            onChange={(step) => onChange({ ...value, step })}
          />
          <NumberField
            label="Folds"
            min={1}
            max={5}
            value={value.folds}
            disabled={!value.backtest}
            onChange={(folds) => onChange({ ...value, folds })}
          />
        </div>
      </fieldset>
      <div className={styles.formGrid}>
        <NumberField
          label="Energy publication lag (h)"
          min={0}
          max={168}
          step={value.frequency === "D" ? 24 : 1}
          value={value.energyLagHours}
          onChange={(energyLagHours) => onChange({ ...value, energyLagHours })}
        />
        <NumberField
          label="Weather publication lag (h)"
          min={0}
          max={336}
          step={value.frequency === "D" ? 24 : 1}
          value={value.weatherLagHours}
          onChange={(weatherLagHours) =>
            onChange({ ...value, weatherLagHours })
          }
        />
      </div>
      {value.weatherVariables.length > 0 && (
        <label className={styles.comparisonToggle}>
          <input
            type="checkbox"
            checked={value.evalNoExog}
            onChange={(event) =>
              onChange({ ...value, evalNoExog: event.target.checked })
            }
          />{" "}
          Also evaluate SARIMAX without weather on the same backtest origins
        </label>
      )}
      <p className={styles.limitNote}>
        Limits: 2–366 training days; horizon ≤168 hourly or 60 daily; p/q ≤3;
        P/Q ≤1; seasonal period ≤168; 5 folds; state-space budget 64 (current
        order: {sarimaxStateCount(value)}). Daily lags must use complete days.
        The issue time follows the exclusive training end plus the energy lag,
        and the model bridges that unavailable gap before the displayed horizon.
      </p>
      {sarimaxStateCount(value) > 64 && (
        <p className={styles.error} role="alert">
          Reduce the seasonal period or orders; this configuration exceeds the
          64-state limit.
        </p>
      )}
      <button
        className={styles.runButton}
        type="submit"
        disabled={disabled || sarimaxStateCount(value) > 64}
      >
        <Play size={15} aria-hidden="true" /> Run SARIMAX job
      </button>
    </form>
  );
}

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  disabled = false,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step?: number;
  disabled?: boolean;
}) {
  return (
    <label>
      {label}
      <input
        type="number"
        required
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

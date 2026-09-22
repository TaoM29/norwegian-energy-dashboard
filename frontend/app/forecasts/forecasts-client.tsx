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
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  CloudSun,
  Database,
  Play,
  Settings2,
  Square,
  X,
  Zap,
} from "lucide-react";
import AnalysisChart from "@/components/analysis-chart";
import { AnalysisShell } from "@/components/analysis-shell";
import {
  DateRangePicker,
  type DateRange,
} from "@/components/date-range-picker";
import { ExportMenu } from "@/components/export-menu";
import { HelpPanel, HelpTip } from "@/components/help";
import { Select } from "@/components/ui/select";
import { areas, number, shiftDay } from "@/lib/api";
import { downloadCsv, downloadJson } from "@/lib/download";
import { writeDashboardUrl } from "@/lib/navigation-state";
import styles from "./forecasts.module.css";
import { ForecastChart, modelColour } from "./forecast-chart";
import { ReliabilityPanel } from "./reliability-panel";
import { AblationPanel } from "./ablation-panel";
import { ErrorExplorer, type ErrorExplorerView, type ErrorExplorerMeasure } from "./error-explorer";

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
  ridge_calendar: "Ridge · calendar",
  ridge_calendar_demand: "Ridge · calendar + demand",
  ridge_calendar_demand_weather: "Ridge · calendar + demand + weather",
  gradient_boosting: "Gradient boosting",
  gradientboosting: "Gradient boosting",
  gb: "Gradient boosting",
  sarimax: "SARIMAX",
  sarimax_no_exog: "SARIMAX without weather",
  sarimax_exog: "SARIMAX with weather",
};
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
  explorer: ErrorExplorerView;
  explorerMeasure: ErrorExplorerMeasure;
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
    explorer: (["area", "season", "peak_period", "horizon"] as const).find(
      (value) => value === query.get("explorer"),
    ) || "area",
    explorerMeasure: query.get("explorerMeasure") === "coverage" ? "coverage" : "error",
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
  const viewRef = useRef<ViewState | null>(null);
  const [results, setResults] = useState<ResultSummary[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [storedDetail, setDetail] = useState<ForecastResult | null>(null);
  const detail = storedDetail?.id === view?.result ? storedDetail : null;
  const [listError, setListError] = useState("");
  const [listRetry, setListRetry] = useState(0);
  const [detailRetry, setDetailRetry] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [jobError, setJobError] = useState("");
  const [runningAction, setRunningAction] = useState(false);
  const [customJobsEnabled, setCustomJobsEnabled] = useState(false);
  const [evaluation, setEvaluation] = useState(defaultEvaluation);
  const [sarimax, setSarimax] = useState(defaultSarimax);
  const [experimentKind, setExperimentKind] =
    useState<Job["kind"]>("evaluation");
  const experimentDialogRef = useRef<HTMLDialogElement>(null);
  const forecastChartRef = useRef<HTMLElement>(null);

  const updateView = useCallback(
    (patch: Partial<ViewState>, replace = true) => {
      const current = viewRef.current;
      if (!current) return;
      const next = { ...current, ...patch };
      // History updates notify Next’s router, so keep them outside React updaters.
      viewRef.current = next;
      setView(next);
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
      params.set("explorer", next.explorer);
      params.set("explorerMeasure", next.explorerMeasure);
      writeDashboardUrl(`?${params}`, { replace });
    },
    [],
  );

  useEffect(() => {
    apiJson<{ customJobsEnabled: boolean }>("/api/forecasts/capabilities")
      .then((value) => setCustomJobsEnabled(value.customJobsEnabled))
      .catch(() => setCustomJobsEnabled(false));
  }, []);

  const loadLists = useCallback(async () => {
    const [resultResponse, jobResponse] = await Promise.allSettled([
      apiJson<{ items: ResultSummary[] }>("/api/forecasts/results"),
      apiJson<{ items: Job[] }>("/api/forecasts/jobs"),
    ]);
    if (jobResponse.status === "fulfilled") {
      setJobs(jobResponse.value.items);
      setJobError("");
    } else {
      setJobError(
        "Job history is unavailable. Saved results can still be explored.",
      );
    }
    if (resultResponse.status === "rejected") throw resultResponse.reason;
    setResults(resultResponse.value.items);
    return {
      results: resultResponse.value.items,
      jobs: jobResponse.status === "fulfilled" ? jobResponse.value.items : [],
    };
  }, []);

  useEffect(() => {
    const restore = () => {
      const next = initialView();
      viewRef.current = next;
      setView(next);
    };
    restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);

  useEffect(() => {
    if (!view) return;
    let live = true;
    setLoading(true);
    setListError("");
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
          setListError(reason.message);
          setLoading(false);
        }
      });
    return () => {
      live = false;
    };
    // Initial list load. Selection changes are handled by the detail effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view ? "ready" : "waiting", loadLists, updateView, listRetry]);

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
        if (controller.signal.aborted) return;
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
          setDetail(null);
          setError(reason.message);
          setLoading(false);
        }
      });
    return () => controller.abort();
    // Result is the only fetch key; filters are client-side.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view?.result, results, detailRetry]);

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
            .filter((row) => {
              const date = targetTime(row).slice(0, 10);
              return (
                (!areaKey(row) || areaKey(row) === view?.area) &&
                (!view?.start || !date || date >= view.start) &&
                (!view?.end || !date || date <= view.end) &&
                (!availableSplits.includes(view?.split || "") ||
                  splitKey(row) === view?.split)
              );
            })
            .map(originKey),
        ),
      ]
        .filter(Boolean)
        .sort(),
    [
      predictionRows,
      view?.area,
      view?.start,
      view?.end,
      view?.split,
      availableSplits,
    ],
  );
  const availableTargetDates = useMemo(
    () =>
      [
        ...new Set(
          predictionRows
            .filter(
              (row) =>
                (!areaKey(row) || areaKey(row) === view?.area) &&
                (!availableSplits.includes(view?.split || "") ||
                  splitKey(row) === view?.split),
            )
            .map(targetTime)
            .filter(Boolean)
            .map((time) => time.slice(0, 10)),
        ),
      ].sort(),
    [predictionRows, view?.area, view?.split, availableSplits],
  );

  useEffect(() => {
    if (
      availableOrigins.length &&
      !availableOrigins.includes(view?.origin || "")
    ) {
      updateView({ origin: availableOrigins.at(-1)! });
    }
  }, [availableOrigins, view?.origin, updateView]);

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

  const forecastPoints = useMemo(
    () =>
      filteredPredictions.map((row) => ({
        time: targetTime(row),
        model: modelKey(row),
        actual: numericValue(row, "actual", "observed"),
        baseline: numericValue(row, "baseline", "seasonalNaive"),
        prediction: numericValue(row, "prediction", "median", "forecast"),
        lower: numericValue(row, "lower", "q10", "lowerBound"),
        upper: numericValue(row, "upper", "q90", "upperBound"),
      })),
    [filteredPredictions],
  );

  const metricSummary = useMemo(() => {
    const summaryRows = metricRows.filter((row) => {
      const scope = textValue(row, "scope", "dimension", "breakdown");
      const rowSplit = explicitSplit(row);
      return (
        (!scope || scope === "overall") &&
        (!view || view.models.includes(modelKey(row))) &&
        (!view ||
          !availableSplits.includes(view.split) ||
          !rowSplit ||
          rowSplit === view.split)
      );
    });
    const ranked = summaryRows
      .map((row) => ({ row, mae: numericValue(row, "mae", "MAE") }))
      .filter((item): item is { row: Json; mae: number } => item.mae != null)
      .sort((a, b) => a.mae - b.mae);
    const sampleSizes = new Set(
      ranked
        .map(({ row }) =>
          numericValue(row, "n", "count", "observations", "points"),
        )
        .filter((value): value is number => value != null),
    );
    const modelCounts = ranked.reduce((counts, { row }) => {
      const model = modelKey(row);
      counts.set(model, (counts.get(model) || 0) + 1);
      return counts;
    }, new Map<string, number>());
    const allRowsHaveSampleSize = ranked.every(
      ({ row }) =>
        numericValue(row, "n", "count", "observations", "points") != null,
    );
    const comparable =
      [...modelCounts.values()].every((count) => count === 1) &&
      (ranked.length <= 1 || (allRowsHaveSampleSize && sampleSizes.size === 1));
    const best = comparable ? ranked[0] || null : null;
    const baselineRow = ranked.find(
      ({ row }) => modelKey(row) === "seasonal_naive",
    );
    const baselineMae = best
      ? (numericValue(best.row, "baselineMae", "baseline_mae") ??
        baselineRow?.mae ??
        null)
      : null;
    const coverage = best
      ? numericValue(best.row, "coverage", "intervalCoverage")
      : null;
    const nominalCoverage = numericValue(
      asObject(detail?.config),
      "interval_coverage",
      "intervalCoverage",
    );
    return {
      rows: filteredMetrics.length,
      models: new Set(filteredMetrics.map(modelKey)).size,
      sampleCount: best
        ? numericValue(best.row, "n", "count", "observations", "points")
        : null,
      bestModel: best ? modelKey(best.row) : "",
      bestMae: best?.mae ?? null,
      baselineMae,
      coverage,
      nominalCoverage,
      comparable,
    };
  }, [availableSplits, detail?.config, filteredMetrics, metricRows, view]);

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
          itemStyle: { color: "#263a32" },
        },
        {
          name: "One-step fitted",
          type: "line",
          data: trainingRows.map((row) => numericValue(row, "fitted")),
          symbol: "none",
          lineStyle: { color: "#3f7eaa", width: 1 },
          itemStyle: { color: "#3f7eaa" },
        },
        {
          name: "Dynamic fitted",
          type: "line",
          data: trainingRows.map((row) => numericValue(row, "dynamic")),
          symbol: "none",
          lineStyle: { color: "#d4774d", width: 1.5, type: "dashed" },
          itemStyle: { color: "#d4774d" },
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
          itemStyle: { color: "#263a32" },
        },
        ...[...byModel.entries()].map(([model, values]) => ({
          name: modelLabel(model),
          type: "line",
          data: times.map((time) =>
            numericValue(values.get(time) || {}, "prediction"),
          ),
          symbol: "circle",
          symbolSize: 4,
          itemStyle: { color: modelColour(model).line },
          lineStyle: {
            color: modelColour(model).line,
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
        "Training dates must include at least 2 days and at most 366 days.",
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
  const reliabilityReport = detail?.reliability;
  const ablationReport = detail?.ablation;
  const isExploratoryStudy =
    asObject(metadata.studyProtocol).evidenceStatus === "exploratory";
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
  const maeChange =
    metricSummary.bestMae != null &&
    metricSummary.baselineMae != null &&
    metricSummary.baselineMae !== 0
      ? ((metricSummary.baselineMae - metricSummary.bestMae) /
          metricSummary.baselineMae) *
        100
      : null;
  const actualCoverage =
    metricSummary.coverage == null
      ? null
      : metricSummary.coverage * (metricSummary.coverage <= 1 ? 100 : 1);
  const nominalCoverage =
    metricSummary.nominalCoverage == null
      ? null
      : metricSummary.nominalCoverage *
        (metricSummary.nominalCoverage <= 1 ? 100 : 1);

  return (
    <AnalysisShell
      title="Forecasts & evaluation"
      description="Compare saved forecasts with actual demand and inspect the evidence behind each model."
    >
      <section
        className={styles.selectorPanel}
        aria-label="Prepared forecast results"
      >
        <div className={styles.resultToolbar}>
          <label>
            Result
            <Select
              aria-label="Prepared forecast result"
              value={view.result}
              onChange={(event) =>
                updateView(
                  {
                    result: event.target.value,
                    start: "",
                    end: "",
                    models: [],
                    origin: "",
                  },
                  false,
                )
              }
            >
              {results.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.title} · {item.kind}
                </option>
              ))}
            </Select>
          </label>
          {customJobsEnabled ? (
            <button
              type="button"
              className={styles.experimentButton}
              onClick={() => experimentDialogRef.current?.showModal()}
            >
              <Settings2 size={15} aria-hidden="true" /> Experiment settings
            </button>
          ) : (
            <a className={styles.methodLink} href="/methods#local-experiments">Methods & local setup</a>
          )}
        </div>
      </section>

      {listError && (
        <section className="analysis-panel">
          <p className={styles.error} role="alert">
            {listError}
          </p>
          <button
            type="button"
            onClick={() => setListRetry((value) => value + 1)}
          >
            Retry results
          </button>
        </section>
      )}
      {error && (
        <section className="analysis-panel">
          <p className={styles.error} role="alert">
            {error}
          </p>
          <button
            type="button"
            onClick={() => setDetailRetry((value) => value + 1)}
          >
            Retry result
          </button>
        </section>
      )}
      {loading && (
        <p role="status" className={styles.loading}>
          Loading stored forecast result…
        </p>
      )}
      {!loading && !error && !listError && !detail && (
        <section className="analysis-panel">
          <h2>No prepared result is available</h2>
          <p>
            {customJobsEnabled
              ? "Open Experiment settings to run an evaluation or SARIMAX job. Completed jobs appear here as saved results."
              : "No saved forecast has been published on this deployment yet. Use a local installation to run an experiment."}
          </p>
        </section>
      )}

      {detail && (
        <>
          <section
            className={styles.resultSummary}
            aria-labelledby="result-summary-title"
          >
            <div className={styles.resultSummaryHeading}>
              <div>
                <h2 id="result-summary-title">{detail.kind === "evaluation" ? "All-area benchmark" : "Saved evaluation"}</h2>
                <HelpTip label="How the summary is calculated">
                  MAE ranking uses overall rows from the selected cohort and
                  only compares models when their sample counts match. Coverage
                  should be read together with interval width in Metric details.
                </HelpTip>
              </div>
              <span>
                {isExploratoryStudy
                  ? "Exploratory · retrospective"
                  : "Retrospective · not operational"}
              </span>
            </div>
            <p className={styles.summaryScope}>
              {detail.kind === "evaluation"
                ? `All ${availableAreas.length} saved areas · ${isExploratoryStudy ? "exploratory study" : view.split.replaceAll("_", " ")}`
                : "Rolling-origin development evaluation"}
              {detail.kind === "evaluation" &&
              ["holdout", "matched_holdout"].includes(view.split) &&
              typeof asObject(detail.coverage).matchedOrigins === "number"
                ? ` · ${asObject(detail.coverage).matchedOrigins} matched area-origins`
                : ""}
              {metricSummary.sampleCount != null
                ? ` · ${number(metricSummary.sampleCount, 0)} target observations per model`
                : ""}
              . Evaluation cohort and included models set these scores; chart area,
              target dates and origin affect only the forecast below.
            </p>
            <div className={styles.evidenceSummaryGrid}>
              <div>
                <span>Average error (MAE)</span>
                <strong>
                  {!metricSummary.comparable
                    ? "Not comparable"
                    : metricSummary.bestMae == null
                      ? "Not recorded"
                      : `${number(metricSummary.bestMae, 0)} kWh`}
                </strong>
                <small>
                  {!metricSummary.comparable
                    ? "Selected models use different sample counts"
                    : metricSummary.bestModel
                      ? modelLabel(metricSummary.bestModel)
                      : "No comparable overall rows"}
                </small>
              </div>
              <div>
                <span>Compared with seasonal pattern</span>
                <strong>
                  {maeChange == null
                    ? "No matched comparison"
                    : metricSummary.bestModel === "seasonal_naive"
                      ? "Reference model"
                      : `${number(Math.abs(maeChange), 1)}% ${maeChange >= 0 ? "lower" : "higher"} MAE`}
                </strong>
                <small>Weekly seasonal reference</small>
              </div>
              <div>
                <span>Outcomes inside interval</span>
                <strong>
                  {actualCoverage == null
                    ? "Not recorded"
                    : `${number(actualCoverage, 1)}%`}
                </strong>
                <small>
                  {nominalCoverage == null
                    ? "No nominal target saved"
                    : metricSummary.bestModel
                      ? `${number(nominalCoverage, 1)}% nominal${actualCoverage != null && actualCoverage < nominalCoverage ? " · Below target" : ""} · ${modelLabel(metricSummary.bestModel)}`
                      : `${number(nominalCoverage, 1)}% nominal`}
                </small>
              </div>
            </div>
          </section>

          {detail.kind === "sarimax" && detail.converged === false && (
            <p className={styles.error} role="alert">
              The optimizer did not converge. Forecasts and nominal intervals
              may be unreliable; reduce the orders or disable seasonality before
              drawing conclusions.
            </p>
          )}

          <section ref={forecastChartRef} tabIndex={-1} aria-label="Selected saved forecast" className={`analysis-panel ${styles.primaryChart}`}>
            <div className={styles.panelHeading}>
              <div>
                <h2>
                  {detail.kind === "sarimax"
                    ? "Forecast and interval"
                    : "Observed and forecast"}
                </h2>
              </div>
              <div className={styles.chartHeadingAside}>
                <span>{summary?.horizon || 24} steps</span>
                <HelpTip label="Forecast uncertainty">
                  Choose which model's stored predictive interval to display.
                  Intervals are conditional on the fitted model; weather
                  uncertainty is included only when the artifact says so.
                  Measured coverage describes the saved evaluation sample, not
                  this single origin.
                </HelpTip>
              </div>
            </div>
            <form
              className={`analysis-controls ${styles.resultFilters}`}
              onSubmit={(event) => event.preventDefault()}
              aria-label="Stored result filters"
            >
              <label>
                Area
                <Select
                  aria-label="Forecast price area"
                  value={view.area}
                  onChange={(event) => updateView({ area: event.target.value })}
                >
                  {availableAreas.map((area) => (
                    <option key={area}>{area}</option>
                  ))}
                </Select>
              </label>
              <DateRangePicker
                label="Target dates"
                value={{ start: view.start, end: view.end }}
                onChange={(range: DateRange) => updateView(range)}
                min={availableTargetDates[0]}
                max={availableTargetDates.at(-1)}
                availableDates={availableTargetDates}
                applyLabel="Apply dates"
              />
              <details className={styles.chartOptions}>
                <summary>Model & evaluation options · {view.models.length} models</summary>
                <div className={styles.chartOptionsBody}>
              {availableSplits.length > 0 && (
                <label>
                  Evaluation cohort
                  <Select
                    aria-label="Evaluation cohort"
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
                          ? isExploratoryStudy
                            ? "Matched exploratory study"
                            : "Matched final holdout (untouched)"
                          : split === "validation"
                            ? "Validation / tuning"
                            : split.replaceAll("_", " ")}
                      </option>
                    ))}
                  </Select>
                </label>
              )}
              {availableOrigins.length > 0 && (
                <label>
                  Matched forecast origin
                  <Select
                    aria-label="Matched forecast origin"
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
                  </Select>
                </label>
              )}
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
                </div>
              </details>
            </form>

            {detail.kind === "sarimax" && (
              <p className={styles.chartContext}>
                Future actuals are unavailable; compare the rolling backtest.
              </p>
            )}
            {filteredPredictions.length ? (
              <ForecastChart
                key={detail.id}
                points={forecastPoints}
                defaultIntervalModel={metricSummary.bestModel}
                nominalCoverage={
                  detail.kind === "sarimax" ? 95 : nominalCoverage
                }
                modelLabel={modelLabel}
                label={`${detail.title} ${view.area} ${view.split} forecast`}
                exports={
                  <>
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
                          failures:
                            detail.failures || detail.backtest?.failures,
                          metadata,
                          filters: view,
                        })
                      }
                    >
                      Download metadata JSON
                    </button>
                  </>
                }
              />
            ) : (
              <p className={styles.empty}>
                No forecast rows match these filters.
              </p>
            )}
          </section>

          {reliabilityReport != null && (
            <ReliabilityPanel
              report={reliabilityReport}
              protocol={metadata.studyProtocol}
              resultId={detail.id}
              unit={typeof metadata.unit === "string" ? metadata.unit : "kWh"}
            />
          )}

          {ablationReport != null && (
            <AblationPanel
              report={ablationReport}
              resultId={detail.id}
              unit={typeof metadata.unit === "string" ? metadata.unit : "kWh"}
            />
          )}

          {detail.kind === "evaluation" && (
            <ErrorExplorer
              metrics={metricRows.filter((row) => !explicitSplit(row) || ["holdout", "matched_holdout"].includes(explicitSplit(row)))}
              predictions={predictionRows.filter((row) => !explicitSplit(row) || ["holdout", "matched_holdout"].includes(explicitSplit(row)))}
              coverage={detail.coverage}
              failures={failures}
              config={detail.config}
              resultId={detail.id}
              exploratory={isExploratoryStudy}
              view={view.explorer}
              measure={view.explorerMeasure}
              onViewChange={(explorer) => updateView({ explorer }, false)}
              onMeasureChange={(explorerMeasure) => updateView({ explorerMeasure }, false)}
              onInspect={({ area, model, origin }) => {
                const rows = predictionRows.filter((row) =>
                  areaKey(row) === area && originKey(row) === origin &&
                  (!explicitSplit(row) || ["holdout", "matched_holdout"].includes(explicitSplit(row))),
                );
                const dates = rows.map(targetTime).filter(Boolean).sort();
                if (!dates.length) return;
                updateView({
                  area, origin,
                  start: dates[0].slice(0, 10),
                  end: dates.at(-1)!.slice(0, 10),
                  models: [...new Set(["seasonal_naive", model])].filter((value) => availableModels.includes(value)),
                  split: explicitSplit(rows[0]) || "matched_holdout",
                }, false);
                forecastChartRef.current?.focus();
                forecastChartRef.current?.scrollIntoView({ block: "start" });
              }}
            />
          )}

          <details className={styles.detailDisclosure}>
            <summary>
              <span>Evidence, availability and limitations</span>
              <small>Source, issue time and publication cutoffs</small>
            </summary>
            <div className={styles.disclosureBody}>
              <section
                className={styles.evidenceStrip}
                aria-label="Forecast evidence context"
              >
                <div>
                  <Database size={17} aria-hidden="true" />
                  <span>Source</span>
                  <strong>
                    {String(source || "Stored versioned artifact")}
                  </strong>
                </div>
                <div>
                  <Clock3 size={17} aria-hidden="true" />
                  <span>Forecast issue</span>
                  <strong>{formatDateTime(issueTime)}</strong>
                </div>
                <div>
                  <Zap size={17} aria-hidden="true" />
                  <span>
                    {detail.kind === "evaluation"
                      ? "Energy eligibility cutoff"
                      : "Last energy available"}
                  </span>
                  <strong>{formatDateTime(lastEnergy)}</strong>
                </div>
                <div>
                  <CloudSun size={17} aria-hidden="true" />
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
                className={
                  upperBound ? styles.upperBound : styles.retrospective
                }
                role="note"
              >
                {upperBound
                  ? "Realized future weather upper bound: this retrospective experiment uses weather that was not available at issue time. It is not an operational forecast."
                  : detail.kind === "sarimax"
                    ? "Retrospective custom experiment using revised snapshots and assumed publication lags. Its projected weather scenario and historical fit are not an as-issued operational forecast."
                    : isExploratoryStudy
                      ? "Exploratory retrospective evaluation on previously reviewed dates: publication lags and historical availability are applied. Results do not establish confirmatory or operational accuracy."
                      : "Retrospective held-out evaluation: publication lags and historical availability are applied. Historical performance does not promise operational accuracy."}
              </p>
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
            </div>
          </details>

          {detail.kind === "sarimax" && trainingRows.length > 0 && (
            <details className={styles.detailDisclosure}>
              <summary>
                <span>In-sample training diagnostics</span>
                <small>{number(numericValue(detail, "aic"), 1)} AIC</small>
              </summary>
              <div className={styles.disclosureBody}>
                <h2>Actual, fitted and dynamic training path</h2>
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
              </div>
            </details>
          )}

          {detail.kind === "sarimax" && backtestRows.length > 0 && (
            <details className={styles.detailDisclosure}>
              <summary>
                <span>Rolling-origin development check</span>
                <small>{detail.backtest?.metrics?.length || 0} models</small>
              </summary>
              <div className={styles.disclosureBody}>
                <h2>Latest matched backtest origin</h2>
                <p>
                  This custom backtest is a development-period diagnostic, not
                  the untouched benchmark holdout. Every displayed model uses
                  the same latest origin and target hours.
                </p>
                <AnalysisChart
                  option={backtestOption}
                  label={`${detail.title} latest rolling backtest`}
                  height={350}
                />
              </div>
            </details>
          )}

          <details className={styles.detailDisclosure}>
            <summary>
              <span>Metric details and downloads</span>
              <small>
                {metricSummary.rows} rows · {metricSummary.models} models
              </small>
            </summary>
            <div className={styles.disclosureBody}>
              <div className={styles.panelHeading}>
                <div>
                  <span className={styles.sectionKicker}>
                    {detail.kind === "sarimax"
                      ? "Rolling-origin development metrics"
                      : ["holdout", "matched_holdout"].includes(view.split)
                        ? isExploratoryStudy
                          ? "Matched exploratory study"
                          : "Untouched final holdout"
                        : "Model development split"}
                  </span>
                  <h2>Accuracy and interval quality</h2>
                  <p>
                    Dates and origin filter the chart only. Area filters
                    area-specific metrics; the Area breakdown compares all regions.
                  </p>
                </div>
                <span>
                  {metricSummary.rows} metric rows · {metricSummary.models}{" "}
                  models
                </span>
              </div>
              <HelpTip label="Metric definitions">
                MAE and RMSE use kWh. Coverage is the share of outcomes inside
                the interval; width measures sharpness, and pinball loss
                evaluates quantiles. MASE scales error by in-sample seasonal
                change. Compare models on the same targets rather than treating
                MASE below one as proof of improvement.
              </HelpTip>
              <label className={styles.metricBreakdownControl}>
                Metric breakdown
                <Select
                  aria-label="Metric breakdown"
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
                </Select>
              </label>
              <MetricTable rows={filteredMetrics} dimension={view.dimension} />
              <details className={styles.allMetrics}>
                <summary>All metrics</summary>
                <p>
                  MAE, RMSE, interval width and quantile losses use kWh. MASE is
                  unitless. Downloads retain every saved metric.
                </p>
                <MetricTable
                  rows={filteredMetrics}
                  dimension={view.dimension}
                  expanded
                />
              </details>
              <div className={styles.tableExport}>
                <ExportMenu label="Export metrics">
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
                </ExportMenu>
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
            </div>
          </details>

          <details className={styles.detailDisclosure}>
            <summary>
              <span>Methods, sources and limitations</span>
              <small>Artifact design and configuration</small>
            </summary>
            <div className={styles.disclosureBody}>
              <p>
                Prepared household-demand benchmarks use all five price areas, a
                24-hour target, baseline, Ridge, gradient boosting and SARIMAX
                on matched origins. Features and lags are defined relative to
                the saved issue time and last available observations.
                {isExploratoryStudy
                  ? " This study covers previously reviewed dates, so its comparisons are exploratory."
                  : " Validation supports tuning; the final holdout remains separate."}
              </p>
              <details>
                <summary>Artifact metadata</summary>
                <pre>
                  {JSON.stringify({ metadata, config: detail.config }, null, 2)}
                </pre>
              </details>
            </div>
          </details>
        </>
      )}

      <dialog
        ref={experimentDialogRef}
        className={styles.experimentDialog}
        aria-labelledby="experiments-title"
      >
        <div className={styles.drawerHeader}>
          <div>
            <span className={styles.sectionKicker}>Bounded compute</span>
            <h2 id="experiments-title">Experiment settings</h2>
          </div>
          <button
            type="button"
            className={styles.drawerClose}
            aria-label="Close experiment settings"
            onClick={() => experimentDialogRef.current?.close()}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <div className={styles.drawerBody}>
          <p className={styles.drawerIntroduction}>
            Compare a prepared set of areas and models, or configure a focused
            SARIMAX forecast. Submitted runs report progress and can be
            cancelled.
          </p>
          <details className={styles.drawerJobs}>
            <summary>
              <span>Job history</span>
              <small>
                {selectedJob
                  ? `${selectedJob.kind} · ${selectedJob.status}`
                  : `${jobs.length} saved jobs`}
              </small>
            </summary>
            <div>
              <label className={styles.jobSelector}>
                Select job
                <Select
                  aria-label="Forecast job history"
                  value={view.job}
                  onChange={(event) => updateView({ job: event.target.value })}
                >
                  <option value="">No job selected</option>
                  {jobs.map((job) => (
                    <option value={job.id} key={job.id}>
                      {job.kind} · {job.status} ·{" "}
                      {formatDateTime(job.createdAt)}
                    </option>
                  ))}
                </Select>
              </label>

              {selectedJob && (
                <section
                  className={styles.selectedJob}
                  aria-label="Selected forecast job"
                >
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
                        onClick={() => {
                          updateView(
                            {
                              result: selectedJob.resultId!,
                              start: "",
                              end: "",
                              models: [],
                              origin: "",
                            },
                            false,
                          );
                          experimentDialogRef.current?.close();
                        }}
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
                    <summary>
                      Submitted configuration and enforced limits
                    </summary>
                    <pre>
                      {JSON.stringify(
                        {
                          config: selectedJob.config,
                          limits: selectedJob.limits,
                        },
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                </section>
              )}
            </div>
          </details>
          {jobError && (
            <p className={styles.error} role="alert">
              {jobError}
            </p>
          )}

          {customJobsEnabled ? (
            <div className={styles.drawerForms}>
              <label className={styles.experimentType}>
                Experiment type
                <Select
                  aria-label="Experiment type"
                  value={experimentKind}
                  onChange={(event) =>
                    setExperimentKind(event.target.value as Job["kind"])
                  }
                >
                  <option value="evaluation">
                    Household-demand evaluation
                  </option>
                  <option value="sarimax">Custom SARIMAX</option>
                </Select>
              </label>
              {experimentKind === "evaluation" ? (
                <EvaluationForm
                  value={evaluation}
                  onChange={setEvaluation}
                  onSubmit={runEvaluation}
                  disabled={runningAction}
                />
              ) : (
                <SarimaxForm
                  value={sarimax}
                  onChange={setSarimax}
                  onSubmit={runSarimax}
                  disabled={runningAction}
                />
              )}
            </div>
          ) : (
            <div className={styles.disabledExperiments}>
              <h3>Prepared results only</h3>
              <p>
                Custom runs are disabled on this deployment. Explore and
                download the saved results, or use a local installation to run
                an experiment.
              </p>
            </div>
          )}
        </div>
      </dialog>
    </AnalysisShell>
  );
}

function MetricTable({
  rows,
  dimension,
  expanded = false,
}: {
  rows: Json[];
  dimension: string;
  expanded?: boolean;
}) {
  if (!rows.length)
    return (
      <p className={styles.empty}>
        No metric rows match this split, model and breakdown.
      </p>
    );
  return (
    <div
      className={styles.tableWrap}
      role="region"
      aria-label={expanded ? "All forecast metrics" : "Forecast comparison"}
      tabIndex={0}
    >
      <table>
        <caption className={styles.tableCaption}>
          {expanded ? "Complete saved metrics" : "Model comparison"} · errors in
          kWh
        </caption>
        <thead>
          <tr>
            <th scope="col">Model</th>
            {dimension !== "overall" && (
              <th scope="col">
                {dimension === "isPeakPeriod" ? "Period" : dimension}
              </th>
            )}
            <th scope="col">MAE</th>
            {expanded ? (
              <>
                <th scope="col">RMSE</th>
                <th scope="col">MASE</th>
                <th scope="col">Baseline MAE</th>
              </>
            ) : (
              <th scope="col">MAE vs baseline</th>
            )}
            <th scope="col">Coverage</th>
            {expanded && (
              <>
                <th scope="col">Mean width</th>
                <th scope="col">Pinball lower</th>
                <th scope="col">Pinball median</th>
                <th scope="col">Pinball upper</th>
              </>
            )}
            <th scope="col">Observations</th>
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
            const mae = numericValue(row, "mae", "MAE");
            const baseline = numericValue(row, "baselineMae", "baseline_mae");
            const change =
              mae != null && baseline != null && baseline > 0
                ? ((mae - baseline) / baseline) * 100
                : null;
            return (
              <tr key={`${modelKey(row)}-${dimensionValue}-${index}`}>
                <th scope="row">{modelLabel(modelKey(row))}</th>
                {dimension !== "overall" && <td>{dimensionValue}</td>}
                <td>{number(mae, 2)}</td>
                {expanded ? (
                  <>
                    <td>{number(numericValue(row, "rmse", "RMSE"), 2)}</td>
                    <td>{number(numericValue(row, "mase", "MASE"), 3)}</td>
                    <td>{number(baseline, 2)}</td>
                  </>
                ) : (
                  <td>
                    {modelKey(row) === "seasonal_naive"
                      ? "Reference"
                      : change == null
                        ? "—"
                        : change === 0
                          ? "Same MAE"
                          : `${number(Math.abs(change), 1)}% ${change < 0 ? "lower" : "higher"}`}
                  </td>
                )}
                <td>
                  {coverage == null
                    ? "—"
                    : `${number(coverage * (coverage <= 1 ? 100 : 1), 1)}%`}
                </td>
                {expanded && (
                  <>
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
                  </>
                )}
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
          <h3>
            Household-demand evaluation{" "}
            <HelpTip label="Matched evaluation">
              Models share the same forecast origins and targets so their
              recorded errors can be compared directly.
            </HelpTip>
          </h3>
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
          <Select
            aria-label="Evaluation weather availability"
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
          </Select>
        </label>
      </div>
      <HelpPanel label="Evaluation dates, limits and weather">
        <p>
          Enter origin dates as comma-separated YYYY-MM-DD values. Validation
          must precede calibration, and calibration must precede the final
          holdout. Limits are 1–48 forecast hours, 30–365 training days, energy
          delay 24–168 hours and weather delay 24–240 hours. Operational weather
          forecasts remain unavailable until archived issue-time data exists.
        </p>
      </HelpPanel>
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
  const trainingEnd = shiftDay(value.end, -1);
  const issueTime = new Date(`${value.end}T00:00:00Z`);
  issueTime.setUTCHours(issueTime.getUTCHours() + value.energyLagHours);
  const targetStepMs = value.frequency === "h" ? 3_600_000 : 86_400_000;
  const forecastWindowEnd = new Date(
    issueTime.getTime() + Math.max(0, value.horizon) * targetStepMs,
  );
  const horizonPresets = value.frequency === "h" ? [24, 72, 168] : [7, 30, 60];
  return (
    <form className={styles.jobForm} onSubmit={onSubmit}>
      <div className={styles.formTitle}>
        <div>
          <h3>
            Custom SARIMAX{" "}
            <HelpTip label="About SARIMAX experiments">
              This model combines an energy time series with optional weather
              regressors. Results are retrospective experiments on revised
              observations, not operational forecasts.
            </HelpTip>
          </h3>
        </div>
        <span>State budget 64</span>
      </div>

      <section
        className={styles.forecastSetup}
        aria-labelledby="forecast-setup-title"
      >
        <div className={styles.setupHeading}>
          <span className={styles.sectionKicker}>Forecast setup</span>
          <h4 id="forecast-setup-title">Training period to forecast horizon</h4>
        </div>
        <div className={styles.setupControls}>
          <DateRangePicker
            label="Training dates"
            value={{ start: value.start, end: trainingEnd }}
            onChange={(range: DateRange) =>
              onChange({
                ...value,
                start: range.start,
                end: shiftDay(range.end, 1),
              })
            }
            disabled={disabled}
          />
          <label>
            Time unit
            <Select
              aria-label="SARIMAX forecast time unit"
              value={value.frequency}
              onChange={(event) => {
                const frequency = event.target
                  .value as SarimaxDraft["frequency"];
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
              <option value="h">Hourly targets</option>
              <option value="D">Daily targets</option>
            </Select>
          </label>
          <NumberField
            label={`Ahead (${value.frequency === "h" ? "hours" : "days"})`}
            min={1}
            max={horizonMax}
            value={value.horizon}
            onChange={(horizon) => onChange({ ...value, horizon })}
          />
          <NumberField
            label="Energy availability delay (hours)"
            min={0}
            max={168}
            step={value.frequency === "D" ? 24 : 1}
            value={value.energyLagHours}
            onChange={(energyLagHours) =>
              onChange({ ...value, energyLagHours })
            }
          />
        </div>
        <div
          className={styles.horizonPresets}
          aria-label="Forecast horizon presets"
        >
          {horizonPresets.map((horizon) => (
            <button
              type="button"
              key={horizon}
              aria-pressed={value.horizon === horizon}
              onClick={() => onChange({ ...value, horizon })}
            >
              {horizon} {value.frequency === "h" ? "hours" : "days"}
            </button>
          ))}
        </div>
        <ol className={styles.forecastFlow}>
          <li>
            <span>1 · Train</span>
            <strong>
              {value.start} – {trainingEnd}
            </strong>
            <small>Inclusive observed period</small>
          </li>
          <li>
            <span>2 · Forecast issue / start</span>
            <strong>{formatDateTime(issueTime.toISOString())}</strong>
            <small>
              Energy data becomes usable {value.energyLagHours} h after the
              training interval closes
            </small>
          </li>
          <li>
            <span>3 · Ahead horizon</span>
            <strong>
              Until {formatDateTime(forecastWindowEnd.toISOString())}
            </strong>
            <small>
              {value.horizon} {value.frequency === "h" ? "hourly" : "daily"}{" "}
              targets · boundary after the final target
            </small>
          </li>
        </ol>
      </section>

      <div className={styles.formGrid}>
        <label>
          Area
          <Select
            aria-label="SARIMAX price area"
            value={value.area}
            onChange={(event) =>
              onChange({ ...value, area: event.target.value })
            }
          >
            {Object.keys(areas).map((area) => (
              <option key={area}>{area}</option>
            ))}
          </Select>
        </label>
        <label>
          Energy kind
          <Select
            aria-label="SARIMAX energy kind"
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
          </Select>
        </label>
        <label>
          Group
          <Select
            aria-label="SARIMAX energy group"
            value={value.group}
            onChange={(event) =>
              onChange({ ...value, group: event.target.value })
            }
          >
            {groups.map((group) => (
              <option key={group}>{group}</option>
            ))}
          </Select>
        </label>
      </div>

      <details className={styles.formDisclosure}>
        <summary>Model structure</summary>
        <div>
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
              {value.seasonalOrder.map((order, index) => (
                <NumberField
                  key={["P", "D", "Q", "s"][index]}
                  label={["P", "D", "Q", "s"][index]}
                  min={index === 3 ? 2 : 0}
                  max={[1, 2, 1, sMax][index]}
                  value={order}
                  disabled={!value.seasonal}
                  onChange={(next) => setSeasonal(index, next)}
                />
              ))}
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
                  onChange({
                    ...value,
                    dynamicStart: Number(event.target.value),
                  })
                }
              />
            </label>
          </fieldset>
        </div>
      </details>

      <details className={styles.formDisclosure}>
        <summary>Weather inputs and availability</summary>
        <div>
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
                          : value.weatherVariables.filter(
                              (item) => item !== key,
                            ),
                      })
                    }
                  />{" "}
                  {label}
                </label>
              ))}
            </div>
          </fieldset>
          <div className={styles.formGrid}>
            <label>
              Future weather
              <Select
                aria-label="SARIMAX future weather assumption"
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
              </Select>
            </label>
            <NumberField
              label="Weather availability delay (hours)"
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
        </div>
      </details>

      <details className={styles.formDisclosure}>
        <summary>Rolling backtest</summary>
        <div>
          <label className={styles.comparisonToggle}>
            <input
              type="checkbox"
              checked={value.backtest}
              onChange={(event) =>
                onChange({ ...value, backtest: event.target.checked })
              }
            />{" "}
            Compare against recorded outcomes at earlier origins
          </label>
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
        </div>
      </details>

      <HelpPanel label="SARIMAX limits and timing">
        <p>
          Training uses 2–366 complete UTC days. Hourly horizons stop at 168 and
          daily horizons at 60. The issue time is the exclusive training end
          plus the energy availability delay; the model bridges that gap before
          returning the requested targets. Daily delays use complete days.
          Orders must remain within the 64-state budget (current order:{" "}
          {sarimaxStateCount(value)}).
        </p>
      </HelpPanel>
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

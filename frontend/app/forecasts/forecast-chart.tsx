"use client";

import { useMemo, useState, type ReactNode } from "react";
import type { EChartsCoreOption } from "echarts/core";
import AnalysisChart from "@/components/analysis-chart";
import { useTheme } from "@/components/theme-provider";
import { Select } from "@/components/ui/select";
import { number } from "@/lib/api";
import styles from "./forecast-chart.module.css";

export type ForecastPoint = {
  time: string;
  model: string;
  actual: number | null;
  baseline: number | null;
  prediction: number | null;
  lower: number | null;
  upper: number | null;
};

type Props = {
  points: ForecastPoint[];
  label: string;
  exports: ReactNode;
  defaultIntervalModel: string;
  nominalCoverage: number | null;
  modelLabel: (model: string) => string;
};

const modelColours: Record<string, { line: string; token: string }> = {
  baseline: { line: "#9a816a", token: "#d3b89e" },
  seasonal_naive: { line: "#9a816a", token: "#d3b89e" },
  ridge: { line: "#176b59", token: "var(--chart-series-1)" },
  gradient_boosting: { line: "#d4774d", token: "#f0936e" },
  sarimax: { line: "#725f9e", token: "var(--chart-series-4)" },
  sarimax_no_exog: { line: "#3f7eaa", token: "var(--chart-series-2)" },
  sarimax_exog: { line: "#a55366", token: "var(--chart-series-5)" },
};
const fallbackColours = [
  { line: "#176b59", token: "var(--chart-series-1)" },
  { line: "#3f7eaa", token: "var(--chart-series-2)" },
  { line: "#d4774d", token: "#f0936e" },
  { line: "#725f9e", token: "var(--chart-series-4)" },
  { line: "#a55366", token: "var(--chart-series-5)" },
];

export function modelColour(model: string) {
  if (modelColours[model]) return modelColours[model];
  // Unknown stored model names still receive a stable color across filters.
  let hash = 0;
  for (const char of model) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return fallbackColours[hash % fallbackColours.length];
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (char) => {
    const entities: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[char];
  });
}

function valueText(value: number | null) {
  return value == null ? "—" : `${number(value, 1)} kWh`;
}

function shortUtcTick(value: string) {
  return value.length >= 16
    ? `${value.slice(5, 10)}\n${value.slice(11, 16)}`
    : value;
}

export function ForecastChart({
  points,
  label,
  exports,
  defaultIntervalModel,
  nominalCoverage,
  modelLabel,
}: Props) {
  const { theme } = useTheme();
  const [intervalChoice, setIntervalChoice] = useState("");
  const models = useMemo(
    () =>
      [...new Set(points.map((point) => point.model))].filter(
        (model) => model !== "baseline" && model !== "seasonal_naive",
      ),
    [points],
  );
  const intervalModels = useMemo(
    () =>
      [...new Set(points.map((point) => point.model))].filter((model) =>
        points.some(
          (point) =>
            point.model === model && point.lower != null && point.upper != null,
        ),
      ),
    [points],
  );
  const intervalModel = intervalModels.includes(intervalChoice)
    ? intervalChoice
    : intervalModels.includes(defaultIntervalModel)
      ? defaultIntervalModel
      : intervalModels[0] || "";
  const sortedPoints = useMemo(
    () =>
      [...points].sort(
        (a, b) =>
          a.time.localeCompare(b.time) || a.model.localeCompare(b.model),
      ),
    [points],
  );
  const times = useMemo(
    () => [...new Set(sortedPoints.map((point) => point.time))].filter(Boolean),
    [sortedPoints],
  );
  const byTime = useMemo(() => {
    const result = new Map<string, ForecastPoint[]>();
    for (const point of sortedPoints) {
      if (!result.has(point.time)) result.set(point.time, []);
      result.get(point.time)!.push(point);
    }
    return result;
  }, [sortedPoints]);
  const firstValue = (time: string, key: "actual" | "baseline") =>
    byTime.get(time)?.find((point) => point[key] != null)?.[key] ?? null;
  const intervalByTime = useMemo(
    () =>
      new Map(
        sortedPoints
          .filter((point) => point.model === intervalModel)
          .map((point) => [point.time, point]),
      ),
    [sortedPoints, intervalModel],
  );
  const hasActual = times.some((time) => firstValue(time, "actual") != null);
  const hasBaseline = times.some(
    (time) => firstValue(time, "baseline") != null,
  );

  const option = useMemo<EChartsCoreOption>(() => {
    const series: Record<string, unknown>[] = [];
    if (intervalModel) {
      const lower = times.map((time) => {
        const point = intervalByTime.get(time);
        return point?.lower != null && point.upper != null ? point.lower : null;
      });
      const width = times.map((time) => {
        const point = intervalByTime.get(time);
        return point?.lower != null && point.upper != null
          ? point.upper - point.lower
          : null;
      });
      const color = modelColour(intervalModel).line;
      series.push(
        {
          name: "Interval base",
          type: "line",
          data: lower,
          stack: "interval",
          stackStrategy: "all",
          symbol: "none",
          silent: true,
          lineStyle: { color, opacity: 0 },
          itemStyle: { color, opacity: 0 },
          areaStyle: { opacity: 0 },
        },
        {
          name: `${modelLabel(intervalModel)} interval band`,
          type: "line",
          data: width,
          stack: "interval",
          stackStrategy: "all",
          symbol: "none",
          silent: true,
          lineStyle: { color, opacity: 0 },
          itemStyle: { color },
          areaStyle: { color, opacity: 0.18 },
        },
      );
    }
    if (hasActual)
      series.push({
        name: "Actual",
        type: "line",
        data: times.map((time) => firstValue(time, "actual")),
        symbol: "none",
        lineStyle: { color: "#263a32", width: 2.2 },
        itemStyle: { color: "#263a32" },
      });
    if (hasBaseline)
      series.push({
        name: "Seasonal baseline",
        type: "line",
        data: times.map((time) => firstValue(time, "baseline")),
        symbol: "none",
        lineStyle: { color: "#9a816a", width: 1.7, type: "dashed" },
        itemStyle: { color: "#9a816a" },
      });
    for (const model of models) {
      const values = new Map(
        sortedPoints
          .filter((point) => point.model === model)
          .map((point) => [point.time, point.prediction]),
      );
      const color = modelColour(model).line;
      series.push({
        name: modelLabel(model),
        type: "line",
        data: times.map((time) => values.get(time) ?? null),
        symbol: times.length < 80 ? "circle" : "none",
        symbolSize: 4,
        lineStyle: { color, width: 2 },
        itemStyle: { color },
      });
    }
    return {
      tooltip: {
        trigger: "axis",
        confine: true,
        extraCssText:
          "max-width: min(360px, calc(100vw - 110px)); white-space: normal; overflow-wrap: anywhere;",
        formatter: (params: unknown) => {
          const first = Array.isArray(params) ? params[0] : params;
          const time =
            first && typeof first === "object" && "axisValue" in first
              ? String(first.axisValue)
              : "";
          const rows = byTime.get(time);
          if (!rows) return "";
          const lines = [`<strong>${escapeHtml(time)} UTC</strong>`];
          const actual = firstValue(time, "actual");
          const baseline = firstValue(time, "baseline");
          if (actual != null) lines.push(`Actual: ${valueText(actual)}`);
          if (baseline != null)
            lines.push(`Seasonal baseline: ${valueText(baseline)}`);
          for (const model of models) {
            const point = rows.find((row) => row.model === model);
            if (point?.prediction != null)
              lines.push(
                `${escapeHtml(modelLabel(model))}: ${valueText(point.prediction)}`,
              );
          }
          const interval = intervalByTime.get(time);
          if (interval?.lower != null && interval.upper != null)
            lines.push(
              `<strong>${escapeHtml(modelLabel(intervalModel))} interval</strong>`,
              `Lower bound: ${valueText(interval.lower)}`,
              `Upper bound: ${valueText(interval.upper)}`,
            );
          return lines.join("<br/>");
        },
      },
      grid: { left: 68, right: 24, top: 24, bottom: 74 },
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
  }, [
    byTime,
    hasActual,
    hasBaseline,
    intervalByTime,
    intervalModel,
    modelLabel,
    models,
    sortedPoints,
    times,
  ]);

  const intervalLabel = intervalModel ? modelLabel(intervalModel) : "";
  const imageOption = useMemo<EChartsCoreOption>(
    () => ({
      title: {
        text: label,
        left: 20,
        top: 12,
        textStyle: {
          fontSize: 15,
          fontWeight: 600,
          width: 820,
          overflow: "truncate",
        },
      },
      legend: {
        type: "plain",
        data: [
          ...(hasActual ? ["Actual"] : []),
          ...(hasBaseline ? ["Seasonal baseline"] : []),
          ...models.map(modelLabel),
          ...(intervalModel ? [`${intervalLabel} interval band`] : []),
        ],
        left: 20,
        right: 20,
        top: 52,
        itemGap: 15,
        itemWidth: 16,
        itemHeight: 8,
        textStyle: { fontSize: 11 },
      },
      grid: { left: 68, right: 24, top: 108, bottom: 74 },
    }),
    [
      hasActual,
      hasBaseline,
      intervalLabel,
      intervalModel,
      label,
      modelLabel,
      models,
    ],
  );
  return (
    <div className={styles.forecastChart}>
      <div className={styles.chartHeader}>
        <div className={styles.chartExplanation}>
          <span>
            {intervalModel
              ? `${nominalCoverage == null ? "Saved" : `${number(nominalCoverage, 0)}% nominal`} interval for ${intervalLabel}; hover to read its lower and upper bounds.`
              : "No stored uncertainty interval is available for these models."}
          </span>
        </div>
        {intervalModels.length > 0 && (
          <label className={styles.intervalControl}>
            Interval model
            <Select
              aria-label="Interval model"
              value={intervalModel}
              disabled={intervalModels.length === 1}
              onChange={(event) => setIntervalChoice(event.target.value)}
            >
              {intervalModels.map((model) => (
                <option key={model} value={model}>
                  {modelLabel(model)}
                </option>
              ))}
            </Select>
          </label>
        )}
      </div>
      <ul className={styles.legend} aria-label="Forecast chart series">
        {hasActual && (
          <li>
            <span
              className={styles.actualSwatch}
              style={{
                backgroundColor: theme === "dark" ? "var(--text)" : "#263a32",
              }}
              aria-hidden="true"
            />
            Actual
          </li>
        )}
        {hasBaseline && (
          <li>
            <span className={styles.baselineSwatch} aria-hidden="true" />
            Seasonal baseline
          </li>
        )}
        {models.map((model) => (
          <li key={model}>
            <span
              className={styles.modelSwatch}
              style={{
                backgroundColor:
                  theme === "dark"
                    ? modelColour(model).token
                    : modelColour(model).line,
              }}
              aria-hidden="true"
            />
            {modelLabel(model)}
          </li>
        ))}
        {intervalModel && (
          <li>
            <span
              className={styles.bandSwatch}
              style={{
                backgroundColor:
                  theme === "dark"
                    ? modelColour(intervalModel).token
                    : modelColour(intervalModel).line,
              }}
              aria-hidden="true"
            />
            {intervalLabel} interval
          </li>
        )}
      </ul>
      <AnalysisChart
        option={option}
        imageOption={imageOption}
        label={label}
        height={400}
        exports={exports}
      />
      <span className={styles.rowCount}>
        {sortedPoints.length} displayed rows
      </span>
      <details className={styles.valuesDisclosure}>
        <summary>View forecast data</summary>
        <div
          className={styles.tableWrap}
          role="region"
          aria-label="Forecast data table"
          tabIndex={0}
        >
          <table>
            <caption>Displayed target times and values, in UTC and kWh</caption>
            <thead>
              <tr>
                <th scope="col">Target time (UTC)</th>
                <th scope="col">Model</th>
                <th scope="col">Actual (kWh)</th>
                <th scope="col">Baseline (kWh)</th>
                <th scope="col">Estimate (kWh)</th>
                <th scope="col">Lower (kWh)</th>
                <th scope="col">Upper (kWh)</th>
              </tr>
            </thead>
            <tbody>
              {sortedPoints.map((point, index) => (
                <tr key={`${point.time}-${point.model}-${index}`}>
                  <th scope="row">{point.time}</th>
                  <td>{modelLabel(point.model)}</td>
                  <td>{number(point.actual, 1)}</td>
                  <td>{number(point.baseline, 1)}</td>
                  <td>{number(point.prediction, 1)}</td>
                  <td>{number(point.lower, 1)}</td>
                  <td>{number(point.upper, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

export default ForecastChart;

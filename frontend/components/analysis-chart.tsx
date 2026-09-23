"use client";

import { type ReactNode, useEffect, useRef } from "react";
import { ExportMenu } from "./export-menu";
import { formatChartNumbers } from "@/lib/chart-format";
import * as echarts from "echarts/core";
import {
  BarChart,
  HeatmapChart,
  LineChart,
  MapChart,
  PieChart,
  ScatterChart,
} from "echarts/charts";
import {
  DataZoomComponent,
  GeoComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  PolarComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption, EChartsType } from "echarts/core";
import { useTheme, type ThemeMode } from "@/components/theme-provider";

echarts.use([
  BarChart,
  HeatmapChart,
  LineChart,
  MapChart,
  PieChart,
  ScatterChart,
  DataZoomComponent,
  GeoComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  PolarComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

type ChartPalette = {
  surface: string;
  text: string;
  muted: string;
  border: string;
  accent: string;
  accentSoft: string;
  grid: string;
  chartText: string;
  series: string[];
  fontFamily: string;
};

function readPalette(): ChartPalette {
  const styles = getComputedStyle(document.documentElement);
  const value = (name: string) => styles.getPropertyValue(name).trim();
  return {
    surface: value("--surface"),
    fontFamily: styles.fontFamily,
    text: value("--text"),
    muted: value("--text-muted"),
    border: value("--border"),
    accent: value("--accent"),
    accentSoft: value("--accent-soft"),
    grid: value("--chart-grid"),
    chartText: value("--chart-text"),
    series: [1, 2, 3, 4, 5].map((index) => value(`--chart-series-${index}`)),
  };
}

function darkColor(value: string, palette: ChartPalette) {
  const normalized = value.toLowerCase().replaceAll(" ", "");
  const replacements: Record<string, string> = {
    "#176b59": palette.series[0],
    "#187566": palette.series[0],
    "#4b9178": "#75c8aa",
    "#39816a": "#75c8aa",
    "#263a32": palette.text,
    "#253b32": palette.text,
    "#344d3c": palette.text,
    "#344c40": palette.text,
    "#607069": palette.chartText,
    "#52645c": palette.chartText,
    "#526a60": palette.chartText,
    "#69776f": palette.chartText,
    "#617269": palette.chartText,
    "#4b6352": palette.chartText,
    "#e4e9e2": palette.grid,
    "#e2e8e2": palette.grid,
    "#e8eeea": palette.grid,
    "#dce3dc": palette.border,
    "#ffffff": palette.surface,
    "#fff": palette.surface,
    "#d4774d": "#f0936e",
    "#725f9e": palette.series[3],
    "#7775a5": palette.series[3],
    "#3f7eaa": palette.series[1],
    "#557c9a": palette.series[1],
    "#a55366": palette.series[4],
    "#d2a83f": palette.series[2],
    "#a87722": palette.series[2],
    "#d18d2f": palette.series[2],
    "#c4942f": palette.series[2],
    "#b88627": palette.series[2],
    "#9a6558": palette.series[4],
    "#9a816a": "#d3b89e",
    "#958573": "#d3b89e",
    "#c55252": "#ee8079",
    "#b84b38": "#ee8079",
    "#a43f35": "#ee8079",
    "#9caaa2": "#94a49c",
    "#a2aea5": "#94a49c",
    "#e3efe9": "rgba(105,199,167,.22)",
    "#eef4ef": "#243b33",
    "#edf3ea": "#294139",
    "#7fb5a1": "#63a98f",
    "#7baa75": "#85c982",
    "rgba(23,107,89,.20)": "rgba(105,199,167,.22)",
    "rgba(23,107,89,.2)": "rgba(105,199,167,.22)",
    "rgba(23,107,89,.14)": "rgba(105,199,167,.18)",
  };
  return replacements[normalized] ?? value;
}

function themedValue(
  value: unknown,
  theme: ThemeMode,
  palette: ChartPalette,
): unknown {
  if (typeof value === "string") {
    return theme === "dark" ? darkColor(value, palette) : value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => themedValue(item, theme, palette));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        themedValue(item, theme, palette),
      ]),
    );
  }
  return value;
}

function componentPatch(value: unknown, patch: Record<string, unknown>) {
  if (Array.isArray(value)) return value.map(() => patch);
  return value == null ? undefined : patch;
}

function styledSeriesPatch(
  value: unknown,
  theme: ThemeMode,
  palette: ChartPalette,
) {
  const series = Array.isArray(value) ? value : value ? [value] : [];
  const styleKeys = [
    "lineStyle",
    "itemStyle",
    "areaStyle",
    "label",
    "endLabel",
    "emphasis",
    "blur",
    "select",
    "markLine",
    "markPoint",
    "markArea",
  ];
  return series.map((item) => {
    if (!item || typeof item !== "object") return {};
    const source = item as Record<string, unknown>;
    const patch: Record<string, unknown> = {};
    if (source.id != null) patch.id = source.id;
    if (source.name != null) patch.name = source.name;
    if (source.color != null)
      patch.color = themedValue(source.color, theme, palette);
    for (const key of styleKeys) {
      if (source[key] != null)
        patch[key] = themedValue(source[key], theme, palette);
    }
    return patch;
  });
}

function themePatch(
  option: EChartsCoreOption,
  theme: ThemeMode,
  palette: ChartPalette,
): EChartsCoreOption {
  const source = option as Record<string, unknown>;
  const axis = {
    axisLine: { lineStyle: { color: palette.border } },
    axisTick: { lineStyle: { color: palette.border } },
    axisLabel: { color: palette.chartText },
    nameTextStyle: { color: palette.chartText },
    splitLine: { lineStyle: { color: palette.grid } },
    minorSplitLine: { lineStyle: { color: palette.grid } },
  };
  const patch: Record<string, unknown> = {
    color: palette.series,
    textStyle: { color: palette.text, fontFamily: palette.fontFamily },
    series: styledSeriesPatch(source.series, theme, palette),
  };
  for (const key of [
    "xAxis",
    "yAxis",
    "angleAxis",
    "radiusAxis",
    "parallelAxis",
    "singleAxis",
  ]) {
    const themedAxis = componentPatch(source[key], axis);
    if (themedAxis) patch[key] = themedAxis;
  }
  const legend = componentPatch(source.legend, {
    textStyle: { color: palette.chartText },
  });
  if (legend) patch.legend = legend;
  const title = componentPatch(source.title, {
    textStyle: { color: palette.text },
    subtextStyle: { color: palette.muted },
  });
  if (title) patch.title = title;
  const tooltip = componentPatch(source.tooltip, {
    backgroundColor: palette.surface,
    borderColor: palette.border,
    textStyle: { color: palette.text },
  });
  if (tooltip) patch.tooltip = tooltip;
  if (source.visualMap != null) {
    const visualMaps = Array.isArray(source.visualMap)
      ? source.visualMap
      : [source.visualMap];
    patch.visualMap = visualMaps.map((item) => {
      const visual =
        item && typeof item === "object"
          ? (item as Record<string, unknown>)
          : {};
      return {
        textStyle: { color: palette.chartText },
        borderColor: palette.border,
        ...(visual.inRange != null
          ? { inRange: themedValue(visual.inRange, theme, palette) }
          : {}),
        ...(visual.outOfRange != null
          ? { outOfRange: themedValue(visual.outOfRange, theme, palette) }
          : {}),
      };
    });
  }
  if (source.geo != null) {
    const geos = Array.isArray(source.geo) ? source.geo : [source.geo];
    patch.geo = geos.map((item) => {
      const geo =
        item && typeof item === "object"
          ? (item as Record<string, unknown>)
          : {};
      return themedValue(
        Object.fromEntries(
          ["itemStyle", "label", "emphasis", "blur", "select"]
            .filter((key) => geo[key] != null)
            .map((key) => [key, geo[key]]),
        ),
        theme,
        palette,
      );
    });
  }
  if (source.dataZoom != null) {
    const zooms = Array.isArray(source.dataZoom)
      ? source.dataZoom
      : [source.dataZoom];
    patch.dataZoom = zooms.map(() => ({
      textStyle: { color: palette.chartText },
      borderColor: palette.border,
      dataBackground: {
        lineStyle: { color: palette.muted },
        areaStyle: { color: palette.grid },
      },
      selectedDataBackground: {
        lineStyle: { color: palette.accent },
        areaStyle: { color: palette.accent, opacity: 0.2 },
      },
      fillerColor: palette.accentSoft,
      handleStyle: { color: palette.surface, borderColor: palette.accent },
      moveHandleStyle: { color: palette.accent },
    }));
  }
  return patch as EChartsCoreOption;
}

function applyTheme(
  instance: EChartsType,
  option: EChartsCoreOption,
  theme: ThemeMode,
) {
  instance.setOption(themePatch(option, theme, readPalette()), {
    notMerge: false,
    lazyUpdate: false,
    silent: true,
  });
}

export default function AnalysisChart({
  option,
  imageOption,
  label,
  height = 340,
  onReady,
  exports,
}: {
  option: EChartsCoreOption;
  imageOption?: EChartsCoreOption;
  label: string;
  height?: number;
  onReady?: (chart: EChartsType) => void;
  exports?: ReactNode;
}) {
  const { theme } = useTheme();
  const node = useRef<HTMLDivElement>(null);
  const chart = useRef<EChartsType | null>(null);
  const ready = useRef(onReady);
  const currentTheme = useRef(theme);
  ready.current = onReady;
  currentTheme.current = theme;
  useEffect(() => {
    if (!node.current) return;
    const instance = echarts.init(node.current, undefined, {
      renderer: "canvas",
    });
    chart.current = instance;
    ready.current?.(instance);
    const resize = new ResizeObserver(() => instance.resize());
    resize.observe(node.current);
    return () => {
      resize.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, []);
  useEffect(() => {
    const instance = chart.current;
    if (!instance) return;
    instance.setOption(
      {
        animation: false,
        textStyle: { fontFamily: readPalette().fontFamily },
        ...formatChartNumbers(option),
      },
      { notMerge: true },
    );
    applyTheme(instance, option, currentTheme.current);
  }, [option]);
  useEffect(() => {
    if (chart.current) applyTheme(chart.current, option, theme);
  }, [theme]);
  function saveImage() {
    if (!chart.current) return;
    const palette = readPalette();
    let imageUrl: string;
    if (imageOption) {
      const source = chart.current;
      const canvas = document.createElement("div");
      const snapshot = echarts.init(canvas, undefined, {
        renderer: "canvas",
        width: Math.max(source.getWidth(), 900),
        height: source.getHeight() + 90,
      });
      try {
        const snapshotOption = {
          ...source.getOption(),
          ...imageOption,
          animation: false,
        } as EChartsCoreOption;
        snapshot.setOption(formatChartNumbers(snapshotOption), { notMerge: true });
        applyTheme(snapshot, snapshotOption, currentTheme.current);
        imageUrl = snapshot.getDataURL({
          type: "png",
          pixelRatio: 2,
          backgroundColor: palette.surface,
        });
      } finally {
        snapshot.dispose();
      }
    } else {
      imageUrl = chart.current.getDataURL({
        type: "png",
        pixelRatio: 2,
        backgroundColor: palette.surface,
      });
    }
    const link = document.createElement("a");
    link.href = imageUrl;
    link.download = `${label
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .slice(0, 80)}.png`;
    link.click();
  }
  return (
    <div className="analysis-chart">
      <div
        ref={node}
        style={{ height, width: "100%", minWidth: 0 }}
        role="img"
        aria-label={label}
      />
      <div className="chart-export">
        <ExportMenu>
          <button
            className="chart-download"
            type="button"
            onClick={saveImage}
            aria-label={`Download ${label} as PNG`}
          >
            Chart image (PNG)
          </button>
          {exports}
        </ExportMenu>
      </div>
    </div>
  );
}

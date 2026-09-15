"use client";

import { useEffect, useRef } from "react";
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

export default function AnalysisChart({
  option,
  label,
  height = 340,
  onReady,
}: {
  option: EChartsCoreOption;
  label: string;
  height?: number;
  onReady?: (chart: EChartsType) => void;
}) {
  const node = useRef<HTMLDivElement>(null);
  const chart = useRef<EChartsType | null>(null);
  const ready = useRef(onReady);
  ready.current = onReady;
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
    chart.current?.setOption(
      {
        animation: false,
        textStyle: { fontFamily: "Arial, sans-serif" },
        ...option,
      },
      { notMerge: true },
    );
  }, [option]);
  function saveImage() {
    if (!chart.current) return;
    const link = document.createElement("a");
    link.href = chart.current.getDataURL({
      type: "png",
      pixelRatio: 2,
      backgroundColor: "#fff",
    });
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
      <button
        className="chart-download"
        type="button"
        onClick={saveImage}
        aria-label={`Download ${label} as PNG`}
      >
        Download chart PNG
      </button>
    </div>
  );
}

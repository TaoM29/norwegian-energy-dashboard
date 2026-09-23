"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart,
  HeatmapChart,
  LineChart,
  MapChart,
} from "echarts/charts";
import {
  DataZoomComponent,
  GeoComponent,
  GridComponent,
  LegendComponent,
  PolarComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import type { EChartsCoreOption, EChartsType } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import {
  Area,
  Brush,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";
import "./trial.css";

echarts.use([
  BarChart,
  CanvasRenderer,
  DataZoomComponent,
  GeoComponent,
  GridComponent,
  HeatmapChart,
  LegendComponent,
  LineChart,
  MapChart,
  PolarComponent,
  TooltipComponent,
  VisualMapComponent,
]);

const green = "#176b59";
const ink = "#344d3c";
const grid = "#e4e9e2";
const axis = { color: "#69776f", fontSize: 11 };

const dates = Array.from({ length: 180 }, (_, index) => {
  const date = new Date(Date.UTC(2026, 0, index + 1));
  const seasonal = Math.sin(index / 14) * 7;
  const demand = 53 + seasonal + Math.cos(index / 5) * 2.4;
  const width = 5 + Math.sin(index / 9) * 1.2;
  const roundedDemand = Number(demand.toFixed(1));
  const lower = Number((demand - width).toFixed(1));
  const upper = Number((demand + width).toFixed(1));
  return {
    date: date.toISOString().slice(0, 10),
    demand: roundedDemand,
    lower,
    band: Number((upper - lower).toFixed(1)),
    upper,
  };
});

const weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const hours = ["00", "04", "08", "12", "16", "20"];
const heatmap = weekdays.flatMap((_, day) =>
  hours.map((_, hour) => [
    hour,
    day,
    Number((2.4 + Math.sin((hour * 4 - 7) / 4) * 0.5 + day * 0.08).toFixed(2)),
  ]),
);
const directions = [
  "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
];
const windFrequency = [7, 5, 4, 3, 4, 5, 6, 8, 11, 10, 8, 7, 6, 5, 6, 5];
const areaValues = [
  { name: "NO 1", value: 61.4 },
  { name: "NO 2", value: 48.2 },
  { name: "NO 3", value: 54.7 },
  { name: "NO 4", value: 51.8 },
  { name: "NO 5", value: 58.9 },
];

function EChart({
  option,
  className = "",
  onChart,
  label,
}: {
  option: EChartsCoreOption;
  className?: string;
  onChart?: (chart: EChartsType) => void;
  label: string;
}) {
  const node = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!node.current) return;
    const chart = echarts.init(node.current, undefined, { renderer: "canvas" });
    chart.setOption(option);
    onChart?.(chart);
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(node.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [onChart, option]);

  return <div ref={node} className={`trial-chart ${className}`} role="img" aria-label={label} />;
}

function standardCartesian() {
  return {
    grid: { left: 52, right: 18, top: 28, bottom: 58 },
    textStyle: { fontFamily: "Arial, sans-serif", color: ink },
    tooltip: { trigger: "axis" },
    xAxis: {
      axisLine: { lineStyle: { color: "#aab7af" } },
      axisLabel: axis,
      splitLine: { show: false },
    },
    yAxis: {
      nameTextStyle: axis,
      axisLabel: axis,
      splitLine: { lineStyle: { color: grid } },
    },
  };
}

export default function ChartTrial() {
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState("");
  const [selectedArea, setSelectedArea] = useState("NO1");
  const mapChart = useRef<EChartsType | null>(null);

  useEffect(() => {
    fetch("/chart-trial/geography")
      .then((response) => {
        if (!response.ok) throw new Error("Geography unavailable");
        return response.json();
      })
      .then((geojson) => {
        echarts.registerMap("norway-price-areas", geojson);
        setMapReady(true);
      })
      .catch(() => setMapError("The trial geography could not be loaded."));
  }, []);

  const timeOption = useMemo<EChartsCoreOption>(() => ({
    ...standardCartesian(),
    animation: false,
    legend: { data: ["Illustrative estimate", "Illustrative 80% interval"], top: 0 },
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => {
        const points = params as Array<{ dataIndex: number }>;
        const row = dates[points[0]?.dataIndex ?? 0];
        return `${row.date}<br/>Estimate: ${row.demand} GWh<br/>80% interval: ${row.lower}–${row.upper} GWh`;
      },
    },
    xAxis: { ...standardCartesian().xAxis, type: "category", data: dates.map((row) => row.date) },
    yAxis: { ...standardCartesian().yAxis, type: "value", min: 35, max: 70, name: "Daily demand (GWh)" },
    dataZoom: [
      { type: "inside", start: 60, end: 100 },
      { type: "slider", start: 60, end: 100, height: 22, bottom: 8 },
    ],
    series: [
      { name: "Interval base", type: "line", data: dates.map((row) => row.lower), stack: "interval", symbol: "none", lineStyle: { opacity: 0 }, areaStyle: { opacity: 0 }, silent: true },
      { name: "Illustrative 80% interval", type: "line", data: dates.map((row) => row.band), stack: "interval", symbol: "none", lineStyle: { opacity: 0 }, itemStyle: { color: "#9bc8b7" }, areaStyle: { color: "#9bc8b7", opacity: 0.42 } },
      { name: "Illustrative estimate", type: "line", data: dates.map((row) => row.demand), symbol: "none", lineStyle: { color: green, width: 2 }, itemStyle: { color: green } },
    ],
  }), []);

  const heatOption = useMemo<EChartsCoreOption>(() => ({
    ...standardCartesian(),
    animation: false,
    grid: { left: 48, right: 30, top: 22, bottom: 58 },
    tooltip: { formatter: (params: unknown) => {
      const point = params as { value: [number, number, number] };
      return `${weekdays[point.value[1]]} ${hours[point.value[0]]}:00<br/>${point.value[2]} GWh`;
    } },
    xAxis: { type: "category", data: hours, name: "Hour (UTC)", axisLabel: axis, splitArea: { show: true } },
    yAxis: { type: "category", data: weekdays, axisLabel: axis, splitArea: { show: true } },
    visualMap: { min: 1.8, max: 3.5, calculable: true, orient: "horizontal", left: "center", bottom: 0, text: ["High", "Low"], inRange: { color: ["#e8f1ed", "#65a58e", "#155e50"] } },
    series: [{ name: "Mean electricity use", type: "heatmap", data: heatmap, label: { show: true, formatter: (p: unknown) => String((p as { value: number[] }).value[2]), fontSize: 10 }, emphasis: { itemStyle: { shadowBlur: 8, shadowColor: "rgba(0,0,0,.25)" } } }],
  }), []);

  const windOption = useMemo<EChartsCoreOption>(() => ({
    animation: false,
    textStyle: { fontFamily: "Arial, sans-serif", color: ink },
    tooltip: { trigger: "item", formatter: "{b}: {c}% of observed hours" },
    polar: { radius: [22, "72%"] },
    angleAxis: { type: "category", data: directions, startAngle: 90, clockwise: true, axisLabel: { ...axis, interval: 1 }, axisLine: { lineStyle: { color: "#aab7af" } } },
    radiusAxis: { name: "Frequency (%)", nameTextStyle: axis, axisLabel: axis, splitLine: { lineStyle: { color: grid } } },
    series: [{ type: "bar", coordinateSystem: "polar", data: windFrequency, barWidth: "88%", itemStyle: { color: green, borderRadius: 2 } }],
  }), []);

  const mapOption = useMemo<EChartsCoreOption>(() => ({
    animation: false,
    tooltip: { trigger: "item", formatter: "{b}<br/>Illustrative demand: {c} GWh" },
    visualMap: { min: 45, max: 65, left: 8, bottom: 6, text: ["65", "45 GWh"], inRange: { color: ["#dfeee8", "#187566"] }, textStyle: axis },
    series: [{
      type: "map",
      map: "norway-price-areas",
      nameProperty: "ElSpotOmr",
      data: areaValues,
      selectedMode: "single",
      roam: true,
      emphasis: { label: { show: true } },
      select: { itemStyle: { areaColor: "#d5aa4e", borderColor: "#253b32", borderWidth: 2 } },
    }],
  }), []);

  const attachMap = useMemo(() => (chart: EChartsType) => {
    mapChart.current = chart;
    chart.dispatchAction({ type: "mapSelect", name: "NO 1" });
    chart.on("click", (event: { name?: string }) => {
      if (event.name?.startsWith("NO ")) {
        const area = event.name;
        setSelectedArea(area.replace(" ", ""));
        queueMicrotask(() => chart.dispatchAction({ type: "mapSelect", name: area }));
      }
    });
  }, []);

  function chooseArea(area: string) {
    const prior = selectedArea.replace("NO", "NO ");
    const next = area.replace("NO", "NO ");
    setSelectedArea(area);
    mapChart.current?.dispatchAction({ type: "mapUnSelect", name: prior });
    mapChart.current?.dispatchAction({ type: "mapSelect", name: next });
  }

  return (
    <main className="trial-page" id="main">
      <a className="trial-back" href="/">← Back to overview</a>
      <header className="trial-intro">
        <div>
          <div className="trial-kicker">Phase 2 · isolated evaluation route</div>
          <h1>Chart library trial.</h1>
        </div>
        <div className="trial-callout">
          <strong>Synthetic fixtures</strong>
          <span>Illustrative values · actual price-area boundaries</span>
        </div>
      </header>

      <section className="trial-matrix" aria-label="Trial coverage">
        {[["Time zoom", "Both"], ["Interval band", "Both"], ["Heatmap", "ECharts"], ["Wind rose", "ECharts"], ["Clickable map", "ECharts"]].map(([name, result]) => <div key={name}><span>{name}</span><strong>{result}</strong></div>)}
      </section>

      <div className="trial-grid">
        <section className="trial-card trial-card-wide">
          <div className="trial-label">ECharts · native dataZoom</div>
          <h2>Time series and uncertainty band</h2>
          <p>Illustrative 80% model interval · excludes weather uncertainty.</p>
          <EChart option={timeOption} label="Illustrative daily demand from January to June 2026 with an 80 percent interval and time zoom" />
          <div className="trial-values" aria-label="Selected interval examples">
            <span>15 May: {dates[134].demand} GWh · {dates[134].lower}–{dates[134].upper}</span>
            <span>15 June: {dates[165].demand} GWh · {dates[165].lower}–{dates[165].upper}</span>
          </div>
        </section>

        <section className="trial-card trial-card-wide">
          <div className="trial-label">Recharts · current dependency</div>
          <h2>Equivalent baseline with Brush</h2>
          <div className="trial-chart trial-chart-short" aria-label="Recharts illustrative daily demand and uncertainty interval">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={dates} margin={{ top: 14, right: 20, bottom: 8, left: 6 }} accessibilityLayer>
                <CartesianGrid stroke={grid} vertical={false} />
                <XAxis dataKey="date" tick={{ fill: axis.color, fontSize: 11 }} minTickGap={42} />
                <YAxis domain={[35, 70]} allowDataOverflow tick={{ fill: axis.color, fontSize: 11 }} label={{ value: "Daily demand (GWh)", angle: -90, position: "insideLeft", fill: axis.color }} />
                <RechartsTooltip content={({ active, label }) => {
                  const row = dates.find((candidate) => candidate.date === label);
                  return active && row ? <div style={{ background: "white", border: `1px solid ${grid}`, padding: 10 }}><strong>{row.date}</strong><br />Estimate: {row.demand} GWh<br />80% interval: {row.lower}–{row.upper} GWh</div> : null;
                }} />
                <Area dataKey="lower" stackId="band" stroke="none" fill="transparent" isAnimationActive={false} />
                <Area name="Illustrative 80% interval" dataKey="band" stackId="band" stroke="none" fill="#9bc8b7" fillOpacity={0.42} isAnimationActive={false} />
                <Line name="Illustrative estimate" dataKey="demand" stroke={green} strokeWidth={2} dot={false} isAnimationActive={false} />
                <Brush dataKey="date" height={24} startIndex={108} travellerWidth={10} stroke={green} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="trial-card">
          <div className="trial-label">ECharts · heatmap</div>
          <h2>Weekly load shape</h2>
          <p>Mean electricity use · weekday and UTC hour</p>
          <EChart option={heatOption} label="Illustrative heatmap of mean electricity use by weekday and UTC hour" />
        </section>

        <section className="trial-card">
          <div className="trial-label">ECharts · polar bar</div>
          <h2>Wind direction frequency</h2>
          <p>Share of hours · %</p>
          <EChart option={windOption} label="Illustrative sixteen-sector wind direction frequency rose" />
          <div className="trial-values"><span>Highest: S 11%</span><span>SSW 10%</span><span>SSE 8%</span><span>SW 8%</span></div>
        </section>

        <section className="trial-card trial-card-wide">
          <div className="trial-label">ECharts · registered repository GeoJSON</div>
          <h2>Clickable price areas</h2>
          <div className="trial-map-layout">
            {mapReady ? <EChart option={mapOption} onChart={attachMap} label="Interactive map of Norway's five electricity price areas" /> : <div className={`trial-chart ${mapError ? "trial-map-error" : ""}`} role="status">{mapError || "Loading Norwegian price areas…"}</div>}
            <div>
              <div className="trial-area-buttons" role="group" aria-label="Norwegian price area">
                {["NO1", "NO2", "NO3", "NO4", "NO5"].map((area) => <button key={area} type="button" aria-pressed={selectedArea === area} onClick={() => chooseArea(area)}>{area} · {areaValues.find((row) => row.name === area.replace("NO", "NO "))?.value} GWh</button>)}
              </div>
              <div className="trial-selected" aria-live="polite"><strong>{selectedArea}</strong> selected · illustrative demand</div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

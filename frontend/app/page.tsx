"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowLeftRight,
  Droplets,
  PlugZap,
  Zap,
  Check,
  ChevronDown,
  Download,
  MapPin,
  RefreshCw,
  Waves,
  type LucideIcon,
} from "lucide-react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { HelpPanel, HelpTip } from "@/components/help";
import { ExportMenu } from "@/components/export-menu";
import { DateRangePicker } from "@/components/date-range-picker";
import { writeDashboardUrl } from "@/lib/navigation-state";
import { RegionComparison } from "@/components/region-comparison";
import { OverviewPeriodComparison } from "@/components/overview-period-comparison";
import { OverviewCaseStudies } from "@/components/overview-case-studies";
import { AppNavigation } from "@/components/app-navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { downloadJson } from "@/lib/download";
import {
  areas,
  Coverage,
  getJson,
  number,
  Overview,
  shiftDay,
  shortDate,
} from "@/lib/api";

type Filters = { area: string; start: string; end: string };
const mixColors: Record<string, string> = {
  hydro: "var(--chart-series-1)",
  wind: "var(--chart-series-2)",
  solar: "var(--chart-series-3)",
  thermal: "var(--chart-series-5)",
  other: "var(--chart-series-4)",
  nuclear: "var(--text-muted)",
};

export default function Page() {
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [filters, setFilters] = useState<Filters | null>(null);
  const [draft, setDraft] = useState<Filters | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const mainRef = useRef<HTMLElement>(null);
  const updateStarted = useRef(0);
  const firstViewRecorded = useRef(false);

  // Local performance evidence: navigation/filter start through a painted result.
  // Two frames include a paint opportunity; no telemetry leaves the browser.
  useEffect(() => {
    if (loading || error || !overview) return;
    let paintedFrame = 0;
    const frame = requestAnimationFrame(() => {
      paintedFrame = requestAnimationFrame(() => {
        const now = performance.now();
        const main = mainRef.current;
        if (!main) return;
        if (!firstViewRecorded.current) {
          main.dataset.firstViewMs = now.toFixed(1);
          firstViewRecorded.current = true;
        }
        main.dataset.updateMs = (now - updateStarted.current).toFixed(1);
        main.dataset.paintedQuery = `${overview.query.area}/${overview.query.start}/${overview.query.end}`;
        updateStarted.current = 0;
      });
    });
    return () => {
      cancelAnimationFrame(frame);
      cancelAnimationFrame(paintedFrame);
    };
  }, [overview, loading, error]);

  useEffect(() => {
    const controller = new AbortController();
    getJson<Coverage>("/api/coverage", controller.signal)
      .then((data) => {
        setCoverage(data);
        const readUrl = () => {
          const params = new URLSearchParams(window.location.search);
          const next = {
            area: params.get("area") || "NO1",
            start: params.get("start") || data.suggestedRange.start,
            end: params.get("end") || shiftDay(data.suggestedRange.end, -1),
          };
          setFilters(next);
          setDraft(next);
          writeDashboardUrl(`?${new URLSearchParams(next)}`, { replace: true });
        };
        readUrl();
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [retry]);

  useEffect(() => {
    if (!coverage) return;
    const restore = () => {
      updateStarted.current = performance.now();
      const params = new URLSearchParams(window.location.search);
      const next = {
        area: params.get("area") || "NO1",
        start: params.get("start") || coverage.suggestedRange.start,
        end: params.get("end") || shiftDay(coverage.suggestedRange.end, -1),
      };
      setFilters(next);
      setDraft(next);
    };
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, [coverage]);

  useEffect(() => {
    if (!filters) return;
    if (!updateStarted.current) updateStarted.current = performance.now();
    const controller = new AbortController();
    setLoading(true);
    setError("");
    let end: string;
    try {
      end = shiftDay(filters.end, 1);
    } catch {
      setError("Choose valid dates for the comparison.");
      setLoading(false);
      return;
    }
    const params = new URLSearchParams({ ...filters, end });
    getJson<Overview>(`/api/overview?${params}`, controller.signal)
      .then(setOverview)
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [filters]);

  function apply(next: Filters) {
    updateStarted.current = performance.now();
    setDraft(next);
    setFilters(next);
    writeDashboardUrl(`?${new URLSearchParams(next)}`);
  }
  function download() {
    if (!overview) return;
    const rows = [
      "date_utc,production_mwh,consumption_mwh,production_partial,consumption_partial",
      ...overview.daily.map((d) =>
        [
          d.date,
          d.production.mwh ?? "",
          d.consumption.mwh ?? "",
          d.production.partial,
          d.consumption.partial,
        ].join(","),
      ),
    ];
    const url = URL.createObjectURL(
      new Blob([rows.join("\n")], { type: "text/csv" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `${overview.query.area}-${overview.query.start}-${overview.query.end}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const selectedArea = overview?.query.area || filters?.area || "NO1";
  const production = overview?.headline.production;
  const consumption = overview?.headline.consumption;
  const partial = production?.partial || consumption?.partial;
  const hydro = overview?.productionMix.find((row) => row.group === "hydro");
  const balance =
    production?.mwh != null && consumption?.mwh != null
      ? (production.mwh - consumption.mwh) / 1000
      : null;
  const trend = overview?.daily.map((d) => ({
    date: d.date,
    production: d.production.partial
      ? null
      : d.production.mwh == null
        ? null
        : d.production.mwh / 1000,
    consumption: d.consumption.partial
      ? null
      : d.consumption.mwh == null
        ? null
        : d.consumption.mwh / 1000,
  }));
  const largest = overview?.productionMix
    .filter((d) => d.share != null)
    .sort((a, b) => (b.share || 0) - (a.share || 0))[0];

  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">
        Skip to overview
      </a>
      <AppNavigation />
      <div className="workspace">
        <main id="main" ref={mainRef} tabIndex={-1}>
          <div className="page-heading">
            <div>
              <h1>Energy overview</h1>
              <p>
                Production, consumption and the balance across Norway’s five
                regions.
              </p>
            </div>
            <div className="page-actions">
              <div className="reading-guide">
                <HelpPanel label="New here? A 30-second guide">
                  <div>
                    <p>
                      Choose a region and time period. <strong>Production</strong>{" "}
                      is electricity generated; <strong>consumption</strong> is
                      electricity used. The chart compares them day by day.
                    </p>
                    <p>
                      NO1–NO5 are Norway’s five electricity price areas. GWh
                      measures energy: 1 GWh is one million kWh. Production minus
                      consumption is an energy balance, not a measurement of
                      exports.
                    </p>
                    <a href="/methods">
                      See the methods, sources and project findings{" "}
                      <ArrowRight size={14} />
                    </a>
                  </div>
                </HelpPanel>
              </div>
              <ExportMenu>
                <Button
                  variant="outline"
                  onClick={download}
                  disabled={!overview || loading || !!error}
                >
                  <Download size={15} /> Export daily data
                </Button>
                <Button
                  variant="outline"
                  disabled={!overview || loading || !!error}
                  onClick={() =>
                    overview &&
                    downloadJson(`${overview.query.area}-overview.json`, overview)
                  }
                >
                  Download data & metadata
                </Button>
              </ExportMenu>
            </div>
          </div>
          <section className="filterbar" aria-label="Overview filters">
            <div className="area-filter">
              <span className="field-label">REGION · PRICE AREA</span>
              <div className="area-tabs" role="group" aria-label="Price area">
                {Object.keys(areas).map((area) => (
                  <button
                    key={area}
                    type="button"
                    aria-pressed={filters?.area === area}
                    onClick={() => draft && apply({ ...draft, area })}
                    disabled={!draft}
                  >
                    {area}
                  </button>
                ))}
              </div>
            </div>
            {draft && (
              <DateRangePicker
                value={draft}
                min={coverage?.coverage.start}
                max={coverage ? shiftDay(coverage.coverage.end, -1) : undefined}
                disabled={loading}
                applyLabel="Apply dates"
                onChange={(range) => apply({ ...draft, ...range })}
              />
            )}
          </section>
          <div className="scope-line">
            <span>
              <MapPin size={14} /> {areas[selectedArea] || selectedArea}{" "}
              <span className="scope-code">{selectedArea}</span>
            </span>
            <span aria-live="polite">
              {loading
                ? "Loading observations…"
                : overview && !error
                  ? `${shortDate(overview.query.start)} ${overview.query.start.slice(0, 4)} – ${shortDate(shiftDay(overview.query.end, -1))} ${shiftDay(overview.query.end, -1).slice(0, 4)} · ${partial ? "Partial coverage" : "Complete daily coverage"}`
                  : "Data unavailable"}
            </span>
          </div>
          {error ? (
            <Card className="state-panel" role="alert">
              <h2>We couldn’t load this view</h2>
              <p>{error}</p>
              <Button
                onClick={() => {
                  setLoading(true);
                  setError("");
                  setRetry((v) => v + 1);
                }}
              >
                <RefreshCw size={15} /> Try again
              </Button>
            </Card>
          ) : !overview ? (
            <div className="state-panel" role="status">
              <Waves size={32} />
              <h2>Gathering the energy picture</h2>
              <p>Reading the validated Elhub observations.</p>
            </div>
          ) : production?.mwh == null && consumption?.mwh == null ? (
            <Card className="state-panel" role="status">
              <Waves size={32} />
              <h2>No observations for these dates</h2>
              <p>
                Choose dates within the available coverage or use the Latest 28
                days shortcut.
              </p>
            </Card>
          ) : (
            <div
              aria-busy={loading}
              className={loading ? "data-content updating" : "data-content"}
            >
              {partial && (
                <div className="notice">
                  Some observations are missing. Totals include only available
                  observations; incomplete days are left as gaps in the chart.
                </div>
              )}
              <section className="metrics" aria-label="Key metrics">
                <Metric
                  title="Energy produced"
                  icon={Zap}
                  tone="production"
                  value={production?.mwh == null ? null : production.mwh / 1000}
                  unit="GWh"
                  note="Across observed production groups"
                />
                <Metric
                  title="Energy consumed"
                  icon={PlugZap}
                  tone="consumption"
                  value={
                    consumption?.mwh == null ? null : consumption.mwh / 1000
                  }
                  unit="GWh"
                  note="Across observed consumption groups"
                />
                <Metric
                  title="Energy balance"
                  icon={ArrowLeftRight}
                  tone="balance"
                  value={balance}
                  unit="GWh"
                  note="Production − consumption; not measured exports"
                />
                <Metric
                  title="Hydropower share"
                  icon={Droplets}
                  tone="hydro"
                  value={hydro?.share == null ? null : hydro.share * 100}
                  unit="%"
                  note="Of observed energy production"
                />
              </section>
              <div className="main-grid">
                <Card className="trend-panel panel">
                  <div className="panel-heading">
                    <div>
                      <div className="eyebrow">DAILY ENERGY</div>
                      <h2>Supply & demand</h2>
                    </div>
                    <div className="legend">
                      <span>
                        <i className="production-dot" /> Production
                      </span>
                      <span>
                        <i className="consumption-dot" /> Consumption
                      </span>
                    </div>
                  </div>
                  <div className="axis-note">GWh / day · UTC</div>
                  <div
                    className="chart"
                    role="img"
                    aria-label="Daily production and consumption. Exact values are in the expandable table below."
                  >
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart
                        data={trend}
                        margin={{ top: 12, right: 10, bottom: 4, left: -16 }}
                        accessibilityLayer
                      >
                        <defs>
                          <linearGradient
                            id="production-fill"
                            x1="0"
                            y1="0"
                            x2="0"
                            y2="1"
                          >
                            <stop
                              offset="0%"
                              stopColor="var(--chart-series-1)"
                              stopOpacity={0.16}
                            />
                            <stop
                              offset="100%"
                              stopColor="var(--chart-series-1)"
                              stopOpacity={0.015}
                            />
                          </linearGradient>
                        </defs>
                        <CartesianGrid
                          stroke="var(--chart-grid)"
                          vertical={false}
                        />
                        <XAxis
                          dataKey="date"
                          tickFormatter={shortDate}
                          tickLine={false}
                          axisLine={false}
                          minTickGap={36}
                          tick={{ fill: "var(--chart-text)", fontSize: 12 }}
                          dy={10}
                        />
                        <YAxis
                          tickLine={false}
                          axisLine={false}
                          tick={{ fill: "var(--chart-text)", fontSize: 12 }}
                        />
                        <Tooltip
                          labelFormatter={(value) => shortDate(String(value))}
                          formatter={(value) => [
                            `${number(Number(value), 2)} GWh`,
                          ]}
                          contentStyle={{
                            border: "1px solid var(--border)",
                            background: "var(--surface)",
                            color: "var(--text)",
                            borderRadius: 12,
                            fontSize: 12,
                          }}
                        />
                        <Area
                          type="linear"
                          dataKey="production"
                          name="Production"
                          stroke="var(--chart-series-1)"
                          fill="url(#production-fill)"
                          strokeWidth={2.4}
                          isAnimationActive={false}
                          connectNulls={false}
                        />
                        <Line
                          type="linear"
                          dataKey="consumption"
                          name="Consumption"
                          stroke="var(--chart-gold)"
                          strokeWidth={2}
                          dot={false}
                          isAnimationActive={false}
                          connectNulls={false}
                        />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="chart-foot">
                    <span>
                      Hourly observations summed into complete UTC days.
                    </span>
                    <span>{overview.daily.length} days</span>
                  </div>
                </Card>
              </div>
              <OverviewPeriodComparison
                overview={overview}
                coverage={coverage}
                updating={loading}
                onSelectPrevious={(range) =>
                  filters && apply({ ...filters, ...range })
                }
              />
              <div className="bottom-grid">
                <Card className="panel mix-panel" id="production">
                  <div className="panel-heading">
                    <div>
                      <div className="eyebrow">GENERATION SOURCES</div>
                      <h2>What powers {selectedArea}?</h2>
                    </div>
                    <span className="small-label">Share of production</span>
                  </div>
                  <div className="mix-bar" aria-hidden="true">
                    {overview.productionMix.map((row) => (
                      <span
                        key={row.group}
                        style={{
                          width: `${(row.share || 0) * 100}%`,
                          background: mixColors[row.group] || "var(--text-muted)",
                        }}
                      />
                    ))}
                  </div>
                  <div className="mix-values">
                    {overview.productionMix.map((row) => (
                      <div key={row.group}>
                        <span>
                          <i
                            style={{
                              background: mixColors[row.group] || "var(--text-muted)",
                            }}
                          />
                          {row.group}
                        </span>
                        <strong>
                          {number(
                            row.share == null ? null : row.share * 100,
                            1,
                          )}
                          <small>%</small>
                        </strong>
                      </div>
                    ))}
                  </div>
                </Card>
                <div className="observation">
                  <span className="observation-icon">
                    <Waves size={21} />
                  </span>
                  <div>
                    <div className="eyebrow">FROM THE OBSERVATIONS</div>
                    <h2>
                      {largest
                        ? `${largest.group.charAt(0).toUpperCase() + largest.group.slice(1)} leads the mix.`
                        : "More observations are needed."}
                    </h2>
                    <p>
                      {largest
                        ? `${number((largest.share || 0) * 100)}% of observed production in ${areas[selectedArea]} came from ${largest.group} over this period.`
                        : "There is no observed production for this selection."}
                    </p>
                    <a href="#daily-data">
                      Explore the underlying values <ArrowRight size={14} />
                    </a>
                  </div>
                </div>
              </div>
              <RegionComparison
                overview={overview}
                onSelect={(area) => filters && apply({ ...filters, area })}
              />
              <OverviewCaseStudies />
              <details id="daily-data" className="daily-table">
                <summary>
                  Daily values{" "}
                  <span>
                    Accessible table · GWh <ChevronDown size={15} />
                  </span>
                </summary>
                <div className="table-scroll">
                  <table>
                    <caption className="sr-only">
                      Daily UTC observations for {selectedArea}. Asterisks mark
                      partial totals.
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">Date (UTC)</th>
                        <th scope="col">Production (GWh)</th>
                        <th scope="col">Consumption (GWh)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overview.daily.map((row) => (
                        <tr key={row.date}>
                          <th scope="row">{row.date}</th>
                          <td>
                            {number(
                              row.production.mwh == null
                                ? null
                                : row.production.mwh / 1000,
                              3,
                            )}
                            {row.production.partial && " *"}
                          </td>
                          <td>
                            {number(
                              row.consumption.mwh == null
                                ? null
                                : row.consumption.mwh / 1000,
                              3,
                            )}
                            {row.consumption.partial && " *"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            </div>
          )}
          <footer id="methods">
            <div>
              <Check size={14} />
              <span>
                Source:{" "}
                <a
                  href="https://elhub.no/data-og-innsikt"
                  target="_blank"
                  rel="noreferrer"
                >
                  Elhub
                </a>{" "}
                · Hourly observed energy · 1 GWh = 1,000 MWh
              </span>
            </div>
            <details>
              <summary>Methods & snapshot</summary>

              <p>
                Production and consumption include base groups only. Unspecified
                and overlapping aggregate groups are excluded. Missing
                observations are never treated as zero. Dates and daily buckets
                use UTC; these are observations, not forecasts.
              </p>
              <p>
                Snapshot:{" "}
                <code>
                  {overview?.snapshot.version ||
                    coverage?.snapshot.version ||
                    "Unavailable"}
                </code>
                . Retrieved{" "}
                {overview?.snapshot.retrievedAt ||
                  coverage?.snapshot.retrievedAt ||
                  "unknown"}
                . This view reads the published snapshot and does not query
                Elhub live.
              </p>
            </details>
          </footer>
        </main>
      </div>
    </div>
  );
}

function Metric({
  title,
  value,
  unit,
  note,
  icon: Icon,
  tone,
}: {
  title: string;
  value: number | null;
  unit: string;
  note: string;
  icon: LucideIcon;
  tone: "production" | "consumption" | "balance" | "hydro";
}) {
  return (
    <div className={`metric metric-${tone}`}>
      <div className="metric-label">
        <span className="metric-title">
          <span className="metric-icon">
            <Icon size={17} strokeWidth={1.7} aria-hidden="true" />
          </span>
          {title}
        </span>
        <HelpTip label={title} iconOnly>
          {note}
        </HelpTip>
      </div>
      <div className="metric-value">
        {number(value)}
        <span>{unit}</span>
      </div>
      <p>{note}</p>
    </div>
  );
}

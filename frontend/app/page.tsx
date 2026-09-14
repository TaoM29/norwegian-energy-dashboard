"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowDownLeft,
  ArrowUpRight,
  ArrowRight,
  BarChart3,
  Check,
  ChevronDown,
  CircleHelp,
  Download,
  Layers3,
  LayoutDashboard,
  MapPin,
  RefreshCw,
  Waves,
  Zap,
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
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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
  hydro: "#187566",
  wind: "#8fbbad",
  solar: "#d8b454",
  thermal: "#958573",
  other: "#c1c9c4",
  nuclear: "#7376a1",
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
    window.history.pushState(null, "", `?${new URLSearchParams(next)}`);
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
      <aside className="sidebar">
        <a href="/" className="brand">
          <span className="brand-mark">
            <Waves size={24} />
          </span>
          <span>
            norwegian<span className="brand-sub">ENERGY OBSERVATORY</span>
          </span>
        </a>
        <div className="nav-label">EXPLORE</div>
        <nav aria-label="Main navigation">
          <a className="nav-item active" href="#main" aria-current="page">
            <LayoutDashboard size={18} /> Overview <span className="nav-dot" />
          </a>
          <a className="nav-item" href="#regions">
            <MapPin size={18} /> Price areas
          </a>
          <a className="nav-item" href="#production">
            <Layers3 size={18} /> Production mix
          </a>
        </nav>
        <div className="sidebar-bottom">
          <span className="small-flag" aria-hidden="true">
            🇳🇴
          </span>
          <p>
            A clearer view of
            <br />
            Norway’s energy.
          </p>
          <a href="#methods">
            <CircleHelp size={16} /> Methods & data
          </a>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>
            Norway <span className="breadcrumb">/</span>{" "}
            <strong>Overview</strong>
          </span>
          <span className="observed-tag">
            <span /> Observed energy data
          </span>
        </header>
        <main id="main" ref={mainRef} tabIndex={-1}>
          <div className="page-heading">
            <div>
              <div className="eyebrow">THE ENERGY PICTURE</div>
              <h1>
                Energy overview<span>.</span>
              </h1>
              <p>Production, consumption and the balance between them.</p>
            </div>
            <Button
              variant="outline"
              onClick={download}
              disabled={!overview || loading || !!error}
            >
              <Download size={15} /> Export daily data
            </Button>
          </div>
          <section className="filterbar" aria-label="Overview filters">
            <div className="area-filter">
              <span className="field-label">PRICE AREA</span>
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
            <form
              onSubmit={(event) => {
                event.preventDefault();
                const dates = new FormData(event.currentTarget);
                if (draft)
                  apply({
                    ...draft,
                    start: String(dates.get("start")),
                    end: String(dates.get("end")),
                  });
              }}
              className="date-filter"
            >
              <label>
                <span className="field-label">FROM · UTC</span>
                <input
                  name="start"
                  aria-label="Start date"
                  type="date"
                  required
                  min={coverage?.coverage.start}
                  max={draft?.end}
                  value={draft?.start || ""}
                  onChange={(e) =>
                    draft && setDraft({ ...draft, start: e.target.value })
                  }
                />
              </label>
              <span className="date-arrow" aria-hidden="true">
                →
              </span>
              <label>
                <span className="field-label">THROUGH · UTC</span>
                <input
                  name="end"
                  aria-label="End date"
                  type="date"
                  required
                  min={draft?.start}
                  max={
                    coverage ? shiftDay(coverage.coverage.end, -1) : undefined
                  }
                  value={draft?.end || ""}
                  onChange={(e) =>
                    draft && setDraft({ ...draft, end: e.target.value })
                  }
                />
              </label>
              <Button
                type="submit"
                variant="outline"
                disabled={!draft || loading}
              >
                Apply
              </Button>
            </form>
            <button
              className="range-reset"
              onClick={() =>
                coverage &&
                apply({
                  area: filters?.area || "NO1",
                  start: coverage.suggestedRange.start,
                  end: shiftDay(coverage.suggestedRange.end, -1),
                })
              }
              disabled={!coverage}
            >
              Last 28 days <RefreshCw size={14} />
            </button>
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
                Choose dates within the available coverage or use Last 28 days.
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
                  value={production?.mwh == null ? null : production.mwh / 1000}
                  unit="GWh"
                  icon={<ArrowUpRight size={18} />}
                  note="Across observed production groups"
                />
                <Metric
                  title="Energy consumed"
                  value={
                    consumption?.mwh == null ? null : consumption.mwh / 1000
                  }
                  unit="GWh"
                  icon={<ArrowDownLeft size={18} />}
                  note="Across observed consumption groups"
                />
                <Metric
                  title="Production − consumption"
                  value={balance}
                  unit="GWh"
                  icon={<Zap size={17} />}
                  note="An energy balance, not measured exports"
                />
                <Metric
                  title="Hydropower share"
                  value={hydro?.share == null ? null : hydro.share * 100}
                  unit="%"
                  icon={<Waves size={18} />}
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
                        <CartesianGrid stroke="#e8eeea" vertical={false} />
                        <XAxis
                          dataKey="date"
                          tickFormatter={shortDate}
                          tickLine={false}
                          axisLine={false}
                          minTickGap={36}
                          tick={{ fill: "#6b7770", fontSize: 11 }}
                          dy={10}
                        />
                        <YAxis
                          tickLine={false}
                          axisLine={false}
                          tick={{ fill: "#6b7770", fontSize: 11 }}
                        />
                        <Tooltip
                          labelFormatter={(value) => shortDate(String(value))}
                          formatter={(value) => [
                            `${number(Number(value), 2)} GWh`,
                          ]}
                          contentStyle={{
                            border: "1px solid #dfe5df",
                            borderRadius: 8,
                            fontSize: 12,
                          }}
                        />
                        <Area
                          type="linear"
                          dataKey="production"
                          name="Production"
                          stroke="#187566"
                          fill="#e3efe9"
                          strokeWidth={2.4}
                          isAnimationActive={false}
                          connectNulls={false}
                        />
                        <Line
                          type="linear"
                          dataKey="consumption"
                          name="Consumption"
                          stroke="#b28c3c"
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
                <Card className="panel regional-panel" id="regions">
                  <div className="panel-heading">
                    <div>
                      <div className="eyebrow">ACROSS NORWAY</div>
                      <h2>Regional consumption</h2>
                    </div>
                    <BarChart3 size={18} className="muted" />
                  </div>
                  <p className="panel-description">
                    Same dates. All five price areas.
                  </p>
                  <ol className="rankings">
                    {overview.regionalRanking.map((row) => (
                      <li key={row.area}>
                        <button
                          onClick={() =>
                            filters && apply({ ...filters, area: row.area })
                          }
                          aria-label={`View ${areas[row.area]}`}
                          className={
                            selectedArea === row.area ? "rank-selected" : ""
                          }
                        >
                          <span className="rank-number">{row.rank ?? "—"}</span>
                          <span className="rank-body">
                            <span className="rank-top">
                              <strong>
                                {row.area} <span>{areas[row.area]}</span>
                              </strong>
                              <span>
                                {number(
                                  row.mwh == null ? null : row.mwh / 1000,
                                  0,
                                )}{" "}
                                <small>GWh{row.partial ? "*" : ""}</small>
                              </span>
                            </span>
                            <span className="rank-track">
                              <span
                                style={{
                                  width: `${row.mwh == null ? 0 : (row.mwh / Math.max(...overview.regionalRanking.map((r) => r.mwh || 0), 1)) * 100}%`,
                                }}
                              />
                            </span>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ol>
                  <p className="ranking-foot">
                    Select a region to explore its energy picture.{" "}
                    {overview.regionalRanking.some((r) => r.partial) &&
                      "* Partial observation coverage."}
                  </p>
                </Card>
              </div>
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
                          background: mixColors[row.group] || "#a5ada8",
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
                              background: mixColors[row.group] || "#a5ada8",
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
  icon,
  note,
}: {
  title: string;
  value: number | null;
  unit: string;
  icon: React.ReactNode;
  note: string;
}) {
  return (
    <div className="metric">
      <div className="metric-label">
        {title}
        <span>{icon}</span>
      </div>
      <div className="metric-value">
        {number(value)}
        <span>{unit}</span>
      </div>
      <p>{note}</p>
    </div>
  );
}

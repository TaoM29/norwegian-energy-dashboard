"use client";

import { useEffect, useState } from "react";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Coverage,
  getJson,
  number,
  Overview,
  Reading,
  shiftDay,
} from "@/lib/api";
import styles from "./overview-insights.module.css";

function complete(reading: Reading) {
  return (
    !reading.partial && reading.mwh != null && Number.isFinite(reading.mwh)
  );
}

function signed(value: number, unit: string) {
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${number(Math.abs(value), 2)} ${unit}`;
}

export function OverviewPeriodComparison({
  overview,
  coverage,
  onSelectPrevious,
  updating = false,
}: {
  overview: Overview;
  coverage: Coverage | null;
  onSelectPrevious: (range: { start: string; end: string }) => void;
  updating?: boolean;
}) {
  const [previous, setPrevious] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const { area, start, end } = overview.query;
  const days = Math.round(
    (Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) /
      86_400_000,
  );
  const previousStart = shiftDay(start, -days);
  const withinCoverage =
    !!coverage &&
    previousStart >= coverage.coverage.start &&
    end <= coverage.coverage.end;

  useEffect(() => {
    const controller = new AbortController();
    setPrevious(null);
    setError("");
    if (withinCoverage) {
      const params = new URLSearchParams({
        area,
        start: previousStart,
        end: start,
      });
      getJson<Overview>(`/api/overview?${params}`, controller.signal)
        .then((data) => {
          if (!controller.signal.aborted) setPrevious(data);
        })
        .catch((reason: Error) => {
          if (!controller.signal.aborted) setError(reason.message);
        });
    }
    return () => controller.abort();
  }, [
    area,
    previousStart,
    start,
    withinCoverage,
    overview.snapshot.version,
    retry,
  ]);

  // Do not pair a new selection with the previous request's response, even for one render.
  const matched =
    previous?.query.area === area &&
    previous.query.start === previousStart &&
    previous.query.end === start
      ? previous
      : null;
  const sameSnapshot = matched?.snapshot.version === overview.snapshot.version;
  const rows = [
    { key: "production" as const, label: "Energy produced" },
    { key: "consumption" as const, label: "Energy consumed" },
  ];
  const incomplete =
    matched &&
    rows.some(
      ({ key }) =>
        !complete(overview.headline[key]) || !complete(matched.headline[key]),
    );

  return (
    <section
      className={styles.comparison}
      aria-labelledby="period-comparison-title"
    >
      <div className={styles.sectionHeading}>
        <div>
          <span className="eyebrow">PUT THIS PERIOD IN CONTEXT</span>
          <h2 id="period-comparison-title">
            What changed from the previous period?
          </h2>
          <p>
            Two consecutive {days}-day windows in {area}. Displayed dates
            include both endpoints; daily totals use UTC.
          </p>
        </div>
      </div>
      {!withinCoverage ? (
        <p className={styles.status}>
          An equal-length comparison needs {previousStart}–{shiftDay(start, -1)}
          .
          {coverage &&
            ` Available dates are ${coverage.coverage.start}–${shiftDay(coverage.coverage.end, -1)}.`}{" "}
          Choose a later or shorter period to compare complete windows.
        </p>
      ) : error ? (
        <div className={styles.status} role="status">
          <p>The previous period could not be loaded. {error}</p>
          <Button
            variant="outline"
            disabled={updating}
            onClick={() => setRetry((value) => value + 1)}
          >
            <RefreshCw size={14} /> Retry comparison
          </Button>
        </div>
      ) : !matched ? (
        <p className={styles.status} role="status">
          Loading the previous {days} days…
        </p>
      ) : (
        <>
          <div className={styles.periods}>
            <span>
              <strong>Selected</strong> {start}–{shiftDay(end, -1)}
            </span>
            <span>
              <strong>Previous</strong> {previousStart}–{shiftDay(start, -1)}
            </span>
          </div>
          <div className={styles.comparisonGrid}>
            {rows.map(({ key, label }) => {
              const current = overview.headline[key];
              const prior = matched.headline[key];
              const comparable =
                sameSnapshot && complete(current) && complete(prior);
              const delta = comparable ? current.mwh! - prior.mwh! : null;
              return (
                <article key={key} className={styles.comparisonMetric}>
                  <h3>{label}</h3>
                  <div className={styles.change}>
                    {delta == null
                      ? "Change unavailable"
                      : signed(delta / 1000, "GWh")}
                  </div>
                  <p>
                    {delta != null && prior.mwh !== 0
                      ? `${signed((delta / prior.mwh!) * 100, "%")} from the previous period`
                      : delta != null
                        ? "Percentage change is undefined from a zero baseline."
                        : !sameSnapshot
                          ? "Both periods must use the same source snapshot."
                          : "Complete observations in both periods are required."}
                  </p>
                  <dl>
                    <div>
                      <dt>Selected</dt>
                      <dd>
                        {number(
                          current.mwh == null ? null : current.mwh / 1000,
                          2,
                        )}{" "}
                        GWh{current.partial && " *"}
                      </dd>
                    </div>
                    <div>
                      <dt>Previous</dt>
                      <dd>
                        {number(prior.mwh == null ? null : prior.mwh / 1000, 2)}{" "}
                        GWh{prior.partial && " *"}
                      </dd>
                    </div>
                  </dl>
                </article>
              );
            })}
          </div>
          <div className={styles.comparisonFoot}>
            <p>
              {!sameSnapshot
                ? "The snapshot changed between requests. Reload the overview before comparing totals."
                : incomplete
                  ? "* Partial totals include available observations only. Changes are withheld wherever either period is incomplete."
                  : "Equal duration makes totals comparable; weekday mix, season and weather may still differ. A change alone does not identify its cause."}
            </p>
            <Button
              variant="outline"
              disabled={updating}
              onClick={() =>
                onSelectPrevious({
                  start: previousStart,
                  end: shiftDay(start, -1),
                })
              }
            >
              <ArrowLeft size={14} /> View previous period
            </Button>
          </div>
        </>
      )}
    </section>
  );
}

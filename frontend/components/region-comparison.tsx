"use client";

import { Select } from "./ui/select";
import { useEffect, useRef, useState } from "react";
import { ArrowDownWideNarrow, ArrowRight, MapPin, X } from "lucide-react";
import { areas, getJson, number, shiftDay, type Overview } from "@/lib/api";
import "./region-comparison.css";

export function RegionComparison({
  overview,
  onSelect,
}: {
  overview: Overview;
  onSelect: (area: string) => void;
}) {
  const [sort, setSort] = useState("consumption");
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const rows = [...overview.regionalRanking].sort((a, b) =>
    sort === "region"
      ? a.area.localeCompare(b.area)
      : (b.mwh ?? -1) - (a.mwh ?? -1),
  );
  const total = rows.reduce((sum, row) => sum + (row.mwh ?? 0), 0);
  useEffect(() => {
    if (!selected) return;
    dialog.current?.showModal();
    const controller = new AbortController();
    setError("");
    setDetail(null);
    if (selected === overview.query.area) setDetail(overview);
    else {
      const query = new URLSearchParams({ ...overview.query, area: selected });
      getJson<Overview>(`/api/overview?${query}`, controller.signal)
        .then(setDetail)
        .catch((reason: Error) => {
          if (reason.name !== "AbortError") setError(reason.message);
        });
    }
    return () => controller.abort();
  }, [selected, overview]);
  function open(area: string, keyboard: boolean) {
    if (dialog.current) dialog.current.dataset.instant = String(keyboard);
    setSelected(area);
  }
  function close() {
    dialog.current?.close();
  }
  return (
    <section className="region-comparison" aria-labelledby="region-table-title">
      <div className="region-table-toolbar">
        <div>
          <h2 id="region-table-title">
            Regional consumption <span className="count-badge">5</span>
          </h2>
          <p>Same dates. All five price areas. Select a region for details.</p>
        </div>
        <label className="sort-pill">
          <ArrowDownWideNarrow size={15} />
          <span>Sort by</span>
          <Select
            aria-label="Sort regions"
            value={sort}
            onChange={(event) => setSort(event.target.value)}
          >
            <option value="consumption">Consumption</option>
            <option value="region">Region code</option>
          </Select>
        </label>
      </div>
      <div className="region-table-scroll">
        <table>
          <thead>
            <tr>
              <th>Region</th>
              <th>Consumption</th>
              <th>Share of available total</th>
              <th>Coverage</th>
              <th>
                <span className="sr-only">Details</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.area}
                data-selected={overview.query.area === row.area}
              >
                <td>
                  <button
                    className="region-name"
                    onClick={(event) => open(row.area, event.detail === 0)}
                  >
                    <span className={`region-code region-${row.area}`}>
                      {row.area}
                    </span>
                    <span>{areas[row.area]}</span>
                  </button>
                </td>
                <td className="tabular-value">
                  {number(row.mwh == null ? null : row.mwh / 1000)}{" "}
                  <small>GWh</small>
                </td>
                <td>
                  <div className="share-cell">
                    <span className="share-track">
                      <span
                        style={{
                          width: `${row.mwh == null || !total ? 0 : (row.mwh / total) * 100}%`,
                        }}
                      />
                    </span>
                    <span>
                      {row.mwh == null || !total
                        ? "—"
                        : `${number((row.mwh / total) * 100)}%`}
                    </span>
                  </div>
                </td>
                <td>
                  <span
                    className={`coverage-badge ${row.partial || row.mwh == null ? "is-partial" : ""}`}
                  >
                    <i />
                    {row.mwh == null
                      ? "Unavailable"
                      : row.partial
                        ? "Partial"
                        : "Complete"}
                  </span>
                </td>
                <td>
                  <button
                    className="row-detail"
                    aria-label={`Inspect ${areas[row.area]}`}
                    onClick={(event) => open(row.area, event.detail === 0)}
                  >
                    <ArrowRight size={16} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="region-table-footer">
        <span>5 regions · UTC intervals</span>
        <span>
          Available consumption: <strong>{number(total / 1000)} GWh</strong>
          {rows.some((row) => row.partial) &&
            " · Includes partial observations"}
        </span>
      </div>
      <dialog
        ref={dialog}
        className="region-drawer"
        aria-labelledby="region-detail-title"
        onClose={() => setSelected(null)}
        onCancel={() => {
          if (dialog.current) dialog.current.dataset.instant = "true";
        }}
        onClick={(event) => {
          if (event.target === event.currentTarget) {
            const box = event.currentTarget.getBoundingClientRect();
            if (
              event.clientX < box.left ||
              event.clientX > box.right ||
              event.clientY < box.top ||
              event.clientY > box.bottom
            )
              close();
          }
        }}
      >
        <header>
          <span>
            <MapPin size={17} /> Region details
          </span>
          <button onClick={close} aria-label="Close region details">
            <X size={19} />
          </button>
        </header>
        <div className="region-drawer-body">
          <div className="region-identity">
            <span className={`region-code region-${selected}`}>{selected}</span>
            <div>
              <h2 id="region-detail-title">
                {selected ? areas[selected] : "Region"}
              </h2>
              <p>
                {overview.query.start} – {shiftDay(overview.query.end, -1)} ·
                UTC
              </p>
            </div>
          </div>
          {error ? (
            <p role="alert">{error}</p>
          ) : !detail ? (
            <p role="status">Loading region observations…</p>
          ) : (
            <>
              <section className="drawer-section">
                <h3>Energy summary</h3>
                <dl className="drawer-stats">
                  <div>
                    <dt>Produced</dt>
                    <dd>
                      {number(
                        detail.headline.production.mwh == null
                          ? null
                          : detail.headline.production.mwh / 1000,
                      )}{" "}
                      <small>GWh</small>
                    </dd>
                  </div>
                  <div>
                    <dt>Consumed</dt>
                    <dd>
                      {number(
                        detail.headline.consumption.mwh == null
                          ? null
                          : detail.headline.consumption.mwh / 1000,
                      )}{" "}
                      <small>GWh</small>
                    </dd>
                  </div>
                </dl>
                <p>
                  Totals include available observations. Production minus
                  consumption is an energy balance, not measured exports.
                </p>
              </section>
              <section className="drawer-section">
                <h3>Generation mix</h3>
                {detail.productionMix.map((row) => (
                  <div className="drawer-mix" key={row.group}>
                    <span>{row.group}</span>
                    <strong>
                      {row.share == null ? "—" : `${number(row.share * 100)}%`}
                    </strong>
                    <div>
                      <span style={{ width: `${(row.share ?? 0) * 100}%` }} />
                    </div>
                  </div>
                ))}
              </section>
              <section className="drawer-section">
                <h3>Source & coverage</h3>
                <p>{detail.snapshot.source}</p>
                <p>
                  {detail.headline.consumption.partial ||
                  detail.headline.production.partial
                    ? "Partial observations: gaps are retained and totals may be incomplete."
                    : "Complete observation coverage for this area and period."}
                </p>
                <p>
                  Snapshot retrieved:{" "}
                  {detail.snapshot.retrievedAt || "Not recorded"}
                </p>
              </section>
            </>
          )}
        </div>
        <footer>
          <button onClick={close}>Close</button>
          <button
            className="drawer-primary"
            disabled={!detail || !!error}
            onClick={() => {
              if (selected) {
                onSelect(selected);
                close();
              }
            }}
          >
            View this region <ArrowRight size={15} />
          </button>
        </footer>
      </dialog>
    </section>
  );
}

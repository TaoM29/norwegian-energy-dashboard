"use client";

import { areas } from "@/lib/api";
import { formatDateRange } from "./date-range-picker";
import "./applied-filters.css";

export function AppliedFilters({
  dirty,
  start,
  end,
  area,
  onReset,
  loading = false,
}: {
  dirty: boolean;
  start: string;
  end: string;
  area?: string;
  onReset?: () => void;
  loading?: boolean;
}) {
  return (
    <div className="applied-filters" data-pending={dirty && !loading}>
      <span>
        Applied: {area ? `${areas[area] || area} · ` : ""}
        {formatDateRange({ start, end })} · UTC
      </span>
      <span className="applied-filter-state" role="status">
        {loading
          ? "Updating results…"
          : dirty
            ? "Changes not applied"
            : "Filters applied"}
      </span>
      {dirty && onReset && (
        <button type="button" onClick={onReset}>
          Discard changes
        </button>
      )}
    </div>
  );
}

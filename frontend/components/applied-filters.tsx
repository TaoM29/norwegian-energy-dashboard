"use client";

import "./applied-filters.css";

export function AppliedFilters({
  dirty,
  onReset,
  loading = false,
}: {
  dirty: boolean;
  onReset?: () => void;
  loading?: boolean;
}) {
  return (
    <div className="applied-filters" data-pending={dirty && !loading}>
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

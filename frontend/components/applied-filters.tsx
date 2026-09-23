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
  if (loading) return null;
  return (
    <div className="applied-filters" data-pending={dirty}>
      <span className="applied-filter-state" role="status">
        {dirty ? "Changes not applied" : "Filters applied"}
      </span>
      {dirty && onReset && (
        <button type="button" onClick={onReset}>
          Discard changes
        </button>
      )}
    </div>
  );
}

export const DASHBOARD_URL_CHANGE_EVENT = "dashboard:urlchange";

const OBSERVATION_FILTERS_KEY = "energy-dashboard-observation-filters";

type ObservationFilters = {
  area?: string;
  start?: string;
  end?: string;
};

const observationPaths = new Set([
  "/",
  "/explore",
  "/regional",
  "/diagnostics",
]);

function readObservationFilters(): ObservationFilters {
  try {
    const value = window.sessionStorage.getItem(OBSERVATION_FILTERS_KEY);
    if (!value) return {};
    const parsed = JSON.parse(value) as ObservationFilters;
    return {
      area: typeof parsed.area === "string" ? parsed.area : undefined,
      start: typeof parsed.start === "string" ? parsed.start : undefined,
      end: typeof parsed.end === "string" ? parsed.end : undefined,
    };
  } catch {
    return {};
  }
}

function observationFilters(params: URLSearchParams): ObservationFilters {
  const filters: ObservationFilters = {};
  for (const key of ["area", "start", "end"] as const) {
    const value = params.get(key);
    if (value) filters[key] = value;
  }
  return filters;
}

function rememberObservationFilters(params: URLSearchParams) {
  const filters = observationFilters(params);
  try {
    window.sessionStorage.setItem(
      OBSERVATION_FILTERS_KEY,
      JSON.stringify(filters),
    );
  } catch {
    // Navigation still works when storage is unavailable.
  }
}

function appendFilters(path: string, filters: ObservationFilters) {
  const params = new URLSearchParams();
  for (const key of ["area", "start", "end"] as const) {
    if (filters[key]) params.set(key, filters[key]);
  }
  return `${path}${params.size ? `?${params}` : ""}`;
}

export function dashboardDestination(path: string) {
  if (typeof window === "undefined") return path;
  const current = new URL(window.location.href);
  const hasObservationScope = observationPaths.has(current.pathname);
  const currentFilters = observationFilters(current.searchParams);

  if (hasObservationScope) rememberObservationFilters(current.searchParams);
  const observationScope = hasObservationScope
    ? currentFilters
    : readObservationFilters();

  if (path === "/forecasts") {
    return appendFilters(path, {
      area: observationScope.area || currentFilters.area,
    });
  }
  return appendFilters(path, {
    ...observationScope,
    area: observationScope.area || currentFilters.area,
  });
}

export function writeDashboardUrl(
  url: string,
  { replace = false }: { replace?: boolean } = {},
) {
  const destination = new URL(url, window.location.href);
  if (destination.href !== window.location.href) {
    const method = replace ? "replaceState" : "pushState";
    window.history[method](window.history.state, "", destination);
  }
  if (observationPaths.has(window.location.pathname)) {
    rememberObservationFilters(new URL(window.location.href).searchParams);
  }
  window.dispatchEvent(new Event(DASHBOARD_URL_CHANGE_EVENT));
}

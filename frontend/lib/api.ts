export type Snapshot = {
  version: string;
  source: string;
  retrievedAt: string | null;
};
export type Reading = {
  mwh: number | null;
  observedHours: number;
  expectedHours: number;
  partial: boolean;
};
export type Coverage = {
  areas: string[];
  coverage: { start: string; end: string };
  suggestedRange: { start: string; end: string };
  snapshot: Snapshot;
};
export type Overview = {
  query: { area: string; start: string; end: string };
  unit: string;
  snapshot: Snapshot;
  headline: { consumption: Reading; production: Reading };
  daily: { date: string; consumption: Reading; production: Reading }[];
  productionMix: (Reading & { group: string; share: number | null })[];
  regionalRanking: (Reading & { rank: number; area: string })[];
};
export const areas: Record<string, string> = {
  NO1: "Eastern Norway",
  NO2: "Southern Norway",
  NO3: "Central Norway",
  NO4: "Northern Norway",
  NO5: "Western Norway",
};
export function shiftDay(date: string, offset: number) {
  const result = new Date(`${date}T00:00:00Z`);
  result.setUTCDate(result.getUTCDate() + offset);
  return result.toISOString().slice(0, 10);
}
export function shortDate(date: string) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(`${date.slice(0, 10)}T00:00:00Z`));
}
export function number(value: number | null | undefined, digits = 1) {
  return value == null
    ? "—"
    : new Intl.NumberFormat("en-GB", { maximumFractionDigits: digits }).format(
        value,
      );
}
export async function getJson<T>(
  url: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : "The data could not be loaded. Check your dates and try again.",
    );
  }
  return response.json();
}

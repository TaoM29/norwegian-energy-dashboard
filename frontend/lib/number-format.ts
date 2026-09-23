/** Presentation only: never use these rounded values in calculations or exports. */
export function formatDisplayValue(value: unknown, digits = 2): string {
  if (value == null) return "—";
  if (typeof value !== "number") return String(value);
  if (!Number.isFinite(value)) return "—";
  if (value !== 0 && Math.abs(value) < 10 ** -digits) {
    return value.toExponential(2);
  }
  const rounded = Number(value.toFixed(digits));
  return new Intl.NumberFormat("en-GB", {
    maximumFractionDigits: digits,
  }).format(Object.is(rounded, -0) ? 0 : rounded);
}

export function chartNumber(value: unknown): string {
  return formatDisplayValue(value, typeof value === "number" && Math.abs(value) >= 1000 ? 0 : 2);
}

/** Keep metadata readable without changing the original downloadable object. */
export function displayJson(value: unknown): string {
  return JSON.stringify(value, (_key, item) => {
    if (typeof item !== "number" || !Number.isFinite(item) || Number.isInteger(item)) return item;
    return Number(Math.abs(item) < 0.001 ? item.toPrecision(3) : item.toFixed(3));
  }, 2);
}

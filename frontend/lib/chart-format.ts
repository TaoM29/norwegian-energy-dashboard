import { chartNumber } from "./number-format";

type Options = Record<string, unknown>;

function withDefaults(value: unknown, defaults: (item: Options) => Options): unknown {
  if (Array.isArray(value)) return value.map((item) => withDefaults(item, defaults));
  if (!value || typeof value !== "object") return value;
  const item = value as Options;
  return { ...defaults(item), ...item };
}

export function formatChartNumbers(option: Options): Options {
  const formatted = { ...option };
  if (option.tooltip) {
    formatted.tooltip = withDefaults(option.tooltip, () => ({
      valueFormatter: (value: unknown) => Array.isArray(value) ? value.map(chartNumber) : chartNumber(value),
    }));
  }
  for (const key of ["xAxis", "yAxis", "radiusAxis", "angleAxis", "singleAxis"]) {
    if (!option[key]) continue;
    const axes = Array.isArray(option[key]) ? option[key] as Options[] : [option[key] as Options];
    const updated = axes.map((axis) => {
      // Dates and category labels must retain their original representation.
      if (axis.type !== "value" && axis.type !== "log") return axis;
      const pointer = (axis.axisPointer || {}) as Options;
      return {
        ...axis,
        axisLabel: { formatter: chartNumber, ...(axis.axisLabel as Options | undefined) },
        axisPointer: {
          ...pointer,
          label: {
            formatter: (params: { value: unknown }) => chartNumber(params.value),
            ...(pointer.label as Options | undefined),
          },
        },
      };
    });
    formatted[key] = Array.isArray(option[key]) ? updated : updated[0];
  }
  if (option.visualMap) {
    formatted.visualMap = withDefaults(option.visualMap, () => ({ precision: 2 }));
  }
  return formatted;
}

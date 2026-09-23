import { test, expect } from "@playwright/test";
import { chartNumber, displayJson, formatDisplayValue } from "../lib/number-format";
import { formatChartNumbers } from "../lib/chart-format";
import { readFile } from "node:fs/promises";

test("chart tooltips round measurements while CSV keeps source precision", async ({ page }) => {
  await page.route("**/api/explore/energy?**", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.series = data.series.map((row: Record<string, unknown>) => ({ ...row, valueKwh: 1234.567890123 }));
    await route.fulfill({ response, json: data });
  });
  await page.goto("/explore?area=NO1&start=2025-11-01&end=2025-11-28");
  const chart = page.getByRole("img", { name: "production groups through time", exact: true });
  await expect(chart.locator("canvas")).toBeVisible();
  await chart.hover({ position: { x: 200, y: 150 } });
  await expect(chart).toContainText("1,235");
  await expect(chart).not.toContainText("1234.567890123");
  await page.getByRole("button", { name: "Export", exact: true }).first().click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Data CSV", exact: true }).click();
  const file = await download;
  expect(await readFile((await file.path())!, "utf8")).toContain("1234.567890123");
});

test("display precision is bounded without hiding small nonzero statistics", () => {
  expect(chartNumber(1234567.891234567)).toBe("1,234,568");
  expect(chartNumber(12.345678901)).toBe("12.35");
  expect(formatDisplayValue(0.987654321, 3)).toBe("0.988");
  expect(formatDisplayValue(0.0000123456, 3)).toBe("1.23e-5");
  expect(formatDisplayValue(-0)).toBe("0");
  expect(formatDisplayValue(null)).toBe("—");
  expect(formatDisplayValue(Infinity)).toBe("—");
  expect(formatDisplayValue("2025-11-01T00:00:00Z")).toBe("2025-11-01T00:00:00Z");
});

test("chart formatting preserves source data, dates and explicit formatters", () => {
  const source = {
    tooltip: { trigger: "axis" },
    xAxis: { type: "time" },
    yAxis: { type: "value", axisLabel: { color: "red" } },
    series: [{ data: [["2025-11-01", 1234.567890123]] }],
  };
  const original = JSON.stringify(source);
  const formatted = formatChartNumbers(source) as any;
  expect(formatted.tooltip.valueFormatter(1234.567890123)).toBe("1,235");
  expect(formatted.tooltip.valueFormatter([12.3456789, 0.00012345])).toEqual(["12.35", "1.23e-4"]);
  expect(formatted.yAxis.axisLabel.formatter(12.3456789)).toBe("12.35");
  expect(formatted.xAxis).toBe(source.xAxis);
  expect(formatted.series).toBe(source.series);
  expect(JSON.stringify(source)).toBe(original);

  const explicit = () => "section-specific";
  const custom = formatChartNumbers({
    tooltip: { formatter: explicit, valueFormatter: explicit },
    yAxis: [{ type: "value", axisLabel: { formatter: explicit } }],
  }) as any;
  expect(custom.tooltip.formatter).toBe(explicit);
  expect(custom.tooltip.valueFormatter).toBe(explicit);
  expect(custom.yAxis[0].axisLabel.formatter).toBe(explicit);
});

test("readable metadata leaves the original export payload unchanged", () => {
  const source = { mean: 123.4567890123, p: 0.0000123456789, count: 12345, nested: [0.987654321] };
  const original = JSON.stringify(source);
  expect(JSON.parse(displayJson(source))).toEqual({ mean: 123.457, p: 0.0000123, count: 12345, nested: [0.988] });
  expect(JSON.stringify(source)).toBe(original);
});

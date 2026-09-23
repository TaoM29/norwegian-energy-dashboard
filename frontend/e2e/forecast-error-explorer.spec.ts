import { expect, test, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";

type Row = Record<string, any>;
const createdAt = "2026-01-01T00:00:00Z";
const winter = "2025-01-01T00:00:00Z";
const summer = "2025-07-01T00:00:00Z";

// Internally consistent saved metrics: values here are independently calculated
// from the fixture predictions, rather than mirroring explorer implementation.
function savedResult(id = "error-study", legacy = false) {
  const predictions: Row[] = [];
  for (const [area, origin, estimates] of [
    ["NO1", winter, [98, 124]],
    ["NO1", summer, [80, 150]],
    ["NO2", winter, [99, 119]],
  ] as const) {
    for (let hour = 0; hour < 2; hour++) {
      for (const model of ["seasonal_naive", "ridge"]) {
        const actual = 100 + hour * 20;
        const baseline = actual - 10;
        const prediction = model === "ridge" ? estimates[hour] : baseline;
        predictions.push({
          model, area, origin, cohort: "matched_holdout",
          targetTime: new Date(Date.parse(origin) + hour * 3600000).toISOString(),
          horizon: hour + 1, season: origin === winter ? "winter" : "summer",
          isPeakPeriod: false, actual, baseline, prediction,
          lower: prediction - 5, median: prediction, upper: prediction + 5,
        });
      }
    }
  }
  const metrics: Row[] = [];
  for (const model of ["seasonal_naive", "ridge"]) {
    const groups: [string, string | null, unknown][] = [
      ["overall", null, null], ["area", "area", "NO1"], ["area", "area", "NO2"],
      ["season", "season", "winter"], ["season", "season", "summer"],
      ["horizon", "horizon", 1], ["horizon", "horizon", 2],
      ["peak_period", "isPeakPeriod", false],
    ];
    for (const [scope, key, value] of groups) {
      // An explicitly absent horizon metric must stay unavailable, even though
      // predictions exist. This explorer visualizes the saved metric contract.
      if (model === "ridge" && scope === "horizon" && value === 2) continue;
      const rows = predictions.filter(r => r.model === model && (!key || r[key] === value));
      const mae = rows.reduce((sum, r) => sum + Math.abs(r.actual - r.prediction), 0) / rows.length;
      metrics.push({
        model, scope, ...(key ? { [key]: value } : {}), observations: rows.length,
        origins: new Set(rows.map(r => r.origin)).size,
        ...(!legacy ? {
          areaOrigins: new Set(rows.map(r => `${r.area}/${r.origin}`)).size,
          distinctOriginDates: new Set(rows.map(r => r.origin.slice(0, 10))).size,
        } : {}),
        mae, baselineMae: 10, maeDeltaVsBaseline: mae - 10,
        intervalCoverage: rows.filter(r => r.actual >= r.lower && r.actual <= r.upper).length / rows.length,
      });
    }
  }
  // Different-cohort data must not leak into this matched-study explorer.
  metrics.push({ model: "ridge", scope: "area", area: "NO1", cohort: "validation", maeDeltaVsBaseline: 999999, observations: 999 });
  const config = { areas: ["NO1", "NO2", "NO3"], models: ["seasonal_naive", "ridge"], horizon_hours: 2, interval_coverage: 0.8 };
  return {
    id, kind: "evaluation", title: legacy ? "Legacy error study" : "Error study", createdAt,
    config, predictions, metrics,
    metadata: { unit: "kWh", studyProtocol: { evidenceStatus: "exploratory" } },
    coverage: {
      attemptedOrigins: 6, matchedOrigins: 3, failedOrigins: 3,
      areas: [
        { area: "NO1", attemptedOrigins: 2, matchedOrigins: 2, excludedOrigins: [] },
        { area: "NO2", attemptedOrigins: 2, matchedOrigins: 1, excludedOrigins: [summer] },
        { area: "NO3", attemptedOrigins: 2, matchedOrigins: 0, excludedOrigins: [winter, summer] },
      ],
    },
    failures: [
      { area: "NO2", model: "ridge", origin: summer, stage: "holdout", reason: "Synthetic failed fit" },
      { area: "NO3", model: "ridge", origin: winter, stage: "holdout", reason: "Synthetic failed fit" },
      { area: "NO3", model: "ridge", origin: summer, stage: "holdout", reason: "Synthetic failed fit" },
      { area: "NO1", model: "ridge", origin: "2024-01-01T00:00:00Z", stage: "calibration", reason: "Separate calibration failure" },
    ],
  };
}

async function mockApi(page: Page) {
  const results = [savedResult(), savedResult("legacy-study", true)];
  await page.route("**/api/forecasts/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/capabilities")) return route.fulfill({ json: { customJobsEnabled: false } });
    if (path.endsWith("/jobs")) return route.fulfill({ json: { items: [], total: 0 } });
    if (path.endsWith("/results")) return route.fulfill({ json: {
      items: results.map(r => ({ id: r.id, kind: r.kind, title: r.title, createdAt,
        areas: r.config.areas, models: r.config.models, start: winter, end: summer,
        horizon: 2, metadata: r.metadata, weatherMode: "historical_only", sourceLabel: "Synthetic test fixture" })), total: results.length,
    } });
    const result = results.find(r => path.endsWith(`/results/${r.id}`));
    if (result) return route.fulfill({ json: result });
    return route.continue();
  });
}

async function choose(page: Page, control: string, option: string) {
  const select = page.getByRole("combobox", { name: control, exact: true });
  if (await select.evaluate(el => el.tagName === "SELECT")) {
    await select.selectOption({ label: option });
  } else {
    await select.click();
    await page.getByRole("option", { name: option, exact: true }).click();
  }
}

test("saved area differences keep missing cells, legacy support, and drill into the correct complete origin", async ({ page }) => {
  await mockApi(page);
  await page.goto("/forecasts?result=legacy-study&area=NO2&start=2025-01-01&end=2025-01-01&explorer=area");
  const explorer = page.getByRole("region", { name: "Forecast error explorer", exact: true });
  await expect(explorer).toBeVisible();
  const matrix = explorer.getByRole("region", { name: "Forecast error matrix" });
  const no1 = matrix.getByRole("row").filter({ has: page.getByRole("rowheader", { name: "NO1", exact: true }) });
  await expect(no1).toContainText("+4");
  await expect(no1).toContainText("4 hours · 2 area-origins · 2 dates");
  await expect(matrix.getByRole("row").filter({ has: page.getByRole("rowheader", { name: "NO2", exact: true }) })).toContainText("-9");
  await expect(matrix.getByRole("row").filter({ has: page.getByRole("rowheader", { name: "NO3", exact: true }) })).toContainText("Unavailable");
  await expect(matrix).not.toContainText("999,999");
  await explorer.getByText("Excluded origins and recorded failures", { exact: true }).click();
  await expect(explorer).toContainText("Synthetic failed fit");
  await expect(explorer).not.toContainText("Separate calibration failure");

  const inspect = matrix.getByRole("button", { name: `Inspect NO1, Ridge, worst saved baseline-relative example at ${summer}`, exact: true });
  await inspect.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/area=NO1/);
  await expect(page).toHaveURL(/start=2025-07-01&end=2025-07-01/);
  await expect(page).toHaveURL(/models=seasonal_naive%2Cridge/);
  const selected = page.getByRole("region", { name: "Selected saved forecast", exact: true });
  await expect(selected).toBeFocused();
  await selected.getByText("View forecast data", { exact: true }).click();
  const chartData = selected.getByRole("region", { name: "Forecast data table", exact: true });
  await expect(chartData.getByRole("row")).toHaveCount(5);
  await expect(chartData).toContainText("2025-07-01T01:00:00.000Z");
  await expect(chartData).not.toContainText("2025-01-01");
  // Inspecting a single origin must not silently narrow the fixed saved matrix.
  await expect(no1).toContainText("+4");
  await page.reload();
  await expect(page.getByRole("region", { name: "Selected saved forecast" })).toContainText("1 Jul 2025");
});

test("explorer view, horizon measure, missing values and exports retain their saved cohort", async ({ page }, testInfo) => {
  await mockApi(page);
  await page.goto("/forecasts?result=error-study&explorer=season");
  const explorer = page.getByRole("region", { name: "Forecast error explorer", exact: true });
  await expect(explorer.getByRole("combobox", { name: "Error explorer view" })).toHaveValue("season");
  await expect(explorer).toContainText(/descriptive/i);
  await expect(explorer.getByRole("row").filter({ hasText: "summer" }).filter({ hasText: "Ridge" })).toContainText("+15 kWh");
  await choose(page, "Error explorer view", "Peak periods");
  await expect(page).toHaveURL(/explorer=peak_period/);
  await expect(explorer).toContainText("Other hours");
  await choose(page, "Error explorer view", "Forecast horizon");
  await choose(page, "Horizon measure", "Observed coverage");
  await expect(page).toHaveURL(/explorer=horizon&explorerMeasure=coverage/);
  await expect(explorer).toContainText("80%");
  await expect(explorer.getByRole("img", { name: /Observed interval coverage/ })).toBeVisible();
  const horizonTable = explorer.getByRole("table");
  await expect(horizonTable.getByRole("row").filter({ hasText: "Hour 1" }).filter({ hasText: "Ridge" })).toContainText("66.7%");
  await expect(horizonTable.getByRole("row").filter({ hasText: "Hour 2" }).filter({ hasText: "Ridge" })).toContainText("Unavailable");
  await explorer.getByRole("button", { name: "Export explorer", exact: true }).click();
  const event = page.waitForEvent("download");
  await page.getByRole("button", { name: "Displayed view JSON", exact: true }).click();
  const download = await event;
  const output = testInfo.outputPath("explorer.json");
  await download.saveAs(output);
  const exported = JSON.parse(await readFile(output, "utf8"));
  expect(exported.resultId).toBe("error-study");
  expect(exported.view).toBe("horizon");
  expect(exported.measure).toBe("coverage");
  expect(exported.cohort.matchedOrigins).toBe(3);
  const ridge = exported.rows.find((row: Row) => row.model === "ridge");
  expect(ridge.maeKwh).toBeCloseTo(23 / 3);
  expect(ridge.observedCoverage).toBeCloseTo(2 / 3);
  expect(ridge.areaOrigins).toBe(3);
  expect(ridge.distinctOriginDates).toBe(2);
  const missing = exported.rows.find((row: Row) => row.model === "ridge" && row.group === "Hour 2");
  expect(missing.savedMetric).toBe(false);
  expect(missing.maeKwh).toBeNull();
  expect(missing.hourlyTargets).toBeNull();
  await page.keyboard.press("Escape");
  await explorer.getByRole("button", { name: "Export", exact: true }).click();
  const png = page.waitForEvent("download");
  await page.getByRole("button", { name: /Download Observed interval coverage.*as PNG/ }).click();
  await (await png).saveAs(testInfo.outputPath("horizon-coverage.png"));
  await page.reload();
  await expect(explorer.getByRole("combobox", { name: "Horizon measure" })).toHaveValue("coverage");
  await page.goBack();
  await expect(explorer.getByRole("combobox", { name: "Horizon measure" })).toHaveValue("error");
});

test("explorer handles invalid URL state and keyboard scrolling on mobile in both themes", async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/forecasts?result=error-study&explorer=invalid&explorerMeasure=invalid");
  const explorer = page.getByRole("region", { name: "Forecast error explorer", exact: true });
  await expect(explorer.getByRole("combobox", { name: "Error explorer view" })).toHaveValue("area");
  for (const theme of ["Light", "Dark"]) {
    await page.getByRole("button", { name: theme, exact: true }).click();
    const matrix = explorer.getByRole("region", { name: "Forecast error matrix" });
    await matrix.focus();
    await matrix.press("ArrowRight");
    await expect.poll(() => matrix.evaluate(el => el.scrollLeft)).toBeGreaterThan(0);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  }
  await choose(page, "Error explorer view", "Forecast horizon");
  await expect(explorer.getByRole("img", { name: /Forecast MAE/ })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

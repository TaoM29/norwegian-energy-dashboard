import { expect, test, type Page } from "@playwright/test";

const origin = "2025-11-01T00:00:00Z";
const models = ["seasonal_naive", "ridge_calendar", "ridge_calendar_demand", "ridge_calendar_demand_weather"];
const features = [
  ["calendar", ["horizon", "hour_sin", "hour_cos"]],
  ["calendar_demand", ["horizon", "hour_sin", "hour_cos", "energy_available", "energy_roll_24_mean"]],
  ["calendar_demand_weather", ["horizon", "hour_sin", "hour_cos", "energy_available", "energy_roll_24_mean", "weather_temperature_2m_roll_24_mean"]],
] as const;

function scores(mae: number) {
  return {
    mae, rmse: mae + 2, bias: 1.2, intervalCoverage: 0.74,
    meanIntervalWidth: 80, pinballLower: 2, pinballMedian: 3, pinballUpper: 4,
  };
}

function fixture(id = "ablation-study") {
  const predictions = [0, 1].flatMap((hour) => models.map((model, index) => ({
    area: "NO1", cohort: "matched_holdout", origin,
    targetTime: new Date(Date.parse(origin) + hour * 3_600_000).toISOString(),
    horizon: hour + 1, model, actual: 100 + hour * 10,
    prediction: 90 + hour * 10 + index * 2, baseline: 90 + hour * 10,
    lower: 80 + hour * 10, median: 90 + hour * 10 + index * 2,
    upper: 110 + hour * 10,
  })));
  const metrics = models.flatMap((model, index) => ["overall", "area"].map((scope) => ({
    model, scope, ...(scope === "area" ? { area: "NO1" } : {}),
    observations: 2, origins: 1, areaOrigins: 1, distinctOriginDates: 1,
    mae: 10 - index * 2, rmse: 12 - index * 2, baselineMae: 10,
    maeDeltaVsBaseline: -index * 2, intervalCoverage: 0.5,
  })));
  return {
    id, kind: "evaluation", title: id === "ablation-study" ? "Step 4 feature study" : "Older result",
    createdAt: "2026-01-01T00:00:00Z", config: {
      areas: ["NO1"], models, horizon_hours: 2, interval_coverage: 0.8,
      weather_mode: "historical_only",
    },
    metadata: { unit: "kWh", studyProtocol: { evidenceStatus: "exploratory" } },
    predictions, metrics, failures: [],
    coverage: { attemptedOrigins: 1, matchedOrigins: 1, failedOrigins: 0 },
    ...(id === "ablation-study" ? { ablation: {
      schemaVersion: 1, evidenceStatus: "exploratory",
      variants: features.map(([featureSet, columns], index) => ({
        model: models[index + 1], featureSet,
        label: ["Calendar only", "Calendar + demand history", "Calendar + demand + eligible weather"][index],
        features: {
          featureSet, selectedGroups: featureSet.split("_"), columns: [...columns],
          groupColumns: { calendar: columns.slice(0, 3) },
        },
        overall: scores(20 - index * 4), byArea: [{ area: "NO1", observations: 1056, origins: 44, ...scores(19 - index * 4) }],
      })),
      support: {
        scheduledDates: 46, observedDates: 44, scheduledAreaOrigins: 230,
        matchedAreaOrigins: 219, excludedAreaOrigins: 11,
        hourlyRowsPerModel: Object.fromEntries(models.map((model) => [model, 5256])),
        missingDates: ["2025-03-14T00:00:00Z"],
      },
      contrasts: [
        { id: "demand", label: "Add demand history", fromModel: models[1], toModel: models[2],
          overall: { mae: -4, rmse: -2, intervalCoverage: 0.02, meanIntervalWidth: 8,
            pinballLower: -1, pinballMedian: -0.5, pinballUpper: 0.5 },
          uncertainty: { byBlockLength: [
            { blockLengthDates: 2, effectiveObservedBlocks: 22, intervals: {
              mae: { lower: -8, upper: -1 }, intervalCoverage: { lower: -0.03, upper: 0.06 },
              pinballLower: { lower: -2, upper: 0.5 },
            }, validResamples: 1000 },
            { blockLengthDates: 4, effectiveObservedBlocks: 11, intervals: { mae: { lower: -9, upper: 2 } }, validResamples: 1000 },
            { blockLengthDates: 8, effectiveObservedBlocks: 5, intervals: null, reason: "Too few date blocks", validResamples: 0 },
          ] } },
        { id: "weather", label: "Add eligible weather", fromModel: models[2], toModel: models[3],
          overall: { mae: 1, rmse: 2, intervalCoverage: -0.01, meanIntervalWidth: -3,
            pinballLower: 0.2, pinballMedian: 0.3, pinballUpper: 0.4 },
          uncertainty: { byBlockLength: [2, 4, 8].map((blockLengthDates) => ({
            blockLengthDates, effectiveObservedBlocks: 5,
            intervals: { mae: { lower: -2, upper: 4 } }, validResamples: 1000,
          })) } },
      ],
    } } : {}),
  };
}

async function mockApi(page: Page) {
  const results = [fixture(), fixture("older-result")];
  await page.route("**/api/forecasts/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/capabilities")) return route.fulfill({ json: { customJobsEnabled: false } });
    if (path.endsWith("/jobs")) return route.fulfill({ json: { items: [], total: 0 } });
    if (path.endsWith("/results")) return route.fulfill({ json: { items: results.map((result) => ({
      id: result.id, kind: result.kind, title: result.title, createdAt: result.createdAt,
      areas: result.config.areas, models, start: origin, end: origin, horizon: 2,
      weatherMode: "historical_only", sourceLabel: "Synthetic test fixture", metadata: result.metadata,
    })) } });
    const selected = results.find((result) => path.endsWith(`/results/${result.id}`));
    if (selected) return route.fulfill({ json: selected });
    return route.continue();
  });
}

test("feature ablation shows fixed-cohort variants, signed contrasts and missing ranges", async ({ page }) => {
  await mockApi(page);
  await page.goto("/forecasts?result=ablation-study");
  const panel = page.getByRole("region", { name: "Feature ablation variant comparison" });
  await expect(page.getByRole("heading", { name: "What each input adds" })).toBeVisible();
  await expect(panel.getByRole("row")).toHaveCount(4);
  await expect(panel.getByRole("row", { name: /Calendar only/ })).toContainText("20");
  await expect(panel.getByRole("row", { name: /Calendar \+ demand history/ })).toContainText("16");
  await expect(panel.getByRole("row", { name: /Calendar \+ demand \+ eligible weather/ })).toContainText("12");
  const contrasts = page.getByRole("region", { name: "Feature ablation added-input contrasts" });
  await expect(contrasts.getByRole("row", { name: /Add demand history/ })).toContainText("-4 kWh");
  await expect(contrasts.getByRole("row", { name: /Add demand history/ })).toContainText("+2 pp");
  await expect(contrasts.getByRole("row", { name: /Add demand history/ })).toContainText("8 dates: Unavailable (Too few date blocks)");
  await expect(contrasts.getByRole("row", { name: /Add eligible weather/ })).toContainText("+1 kWh");
  await expect(page.getByText(/Exclusions and failures reduce the matched cohort/)).toBeVisible();
  await expect(page.getByText(/Missing dates: 2025-03-14/)).toBeVisible();
  await page.getByText("Bias, pinball scores, area results and exact features").click();
  await expect(page.getByText(/same matched, previously reviewed dates/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Calendar + demand + eligible weather details" })).toContainText("weather_temperature_2m_roll_24_mean");
  await expect(page.getByRole("region", { name: "Calendar only area results" })).toContainText("NO1");
  await expect(page.getByRole("region", { name: "Calendar only area results" })).toContainText("1,056");
  await expect(page.getByRole("region", { name: "Added-input pinball changes" })).toContainText("lower -1 kWh");
  const uncertainty = page.getByRole("region", { name: "Add demand history uncertainty ranges" });
  await expect(uncertainty.getByRole("row", { name: /2 dates/ })).toContainText("-3 pp to +6 pp");
  await expect(uncertainty.getByRole("row", { name: /8 dates/ })).toContainText("Unavailable (Too few date blocks)");
  await expect(page.getByRole("link", { name: "Download complete study JSON" })).toHaveAttribute("href", /ablation-study\/artifact$/);
  const chart = page.getByRole("region", { name: "Selected saved forecast" });
  await expect(chart).toContainText("Ridge · calendar + demand + weather");
  expect(await page.getByRole("heading", { name: "What each input adds" }).evaluate((element) => {
    const chart = document.querySelector('[aria-label="Selected saved forecast"]');
    return chart ? Boolean(element.compareDocumentPosition(chart) & Node.DOCUMENT_POSITION_PRECEDING) : false;
  })).toBe(true);
  await page.getByRole("combobox", { name: "Prepared forecast result" }).click();
  await page.getByRole("option", { name: /Older result/ }).click();
  await expect(page.getByRole("heading", { name: "What each input adds" })).toHaveCount(0);
});

test("feature ablation tables stay keyboard scrollable on mobile in both themes", async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/forecasts?result=ablation-study");
  for (const theme of ["Light", "Dark"]) {
    await page.getByRole("button", { name: theme, exact: true }).click();
    const table = page.getByRole("region", { name: "Feature ablation added-input contrasts" });
    await table.focus();
    await table.press("ArrowRight");
    await expect.poll(() => table.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  }
});

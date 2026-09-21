import { expect, test, type Page } from "@playwright/test";

const origin = "2025-11-01T00:00:00Z";
const createdAt = "2026-01-01T00:00:00Z";

function summary(id: string, title: string) {
  return {
    id,
    kind: "evaluation",
    title,
    createdAt,
    issueTime: null,
    areas: ["NO1"],
    start: "2025-11-01",
    end: "2025-11-01",
    horizon: 2,
    models: ["seasonal_naive", "ridge"],
    weatherMode: "historical_only",
    sourceLabel: "Synthetic test fixture",
    metadata: {},
  };
}

function result(id: string, title: string, ridgeMae: number) {
  const observations = [
    { targetTime: origin, actual: 150, baseline: 140, ridge: 148 },
    {
      targetTime: "2025-11-01T01:00:00Z",
      actual: 160,
      baseline: 145,
      ridge: 158,
    },
  ];
  const predictions = observations.flatMap((point, horizon) => [
    {
      area: "NO1",
      cohort: "matched_holdout",
      origin,
      targetTime: point.targetTime,
      horizon: horizon + 1,
      model: "seasonal_naive",
      actual: point.actual,
      prediction: point.baseline,
      baseline: point.baseline,
      lower: 101 + horizon,
      median: 140 + horizon,
      upper: 202 + horizon,
    },
    {
      area: "NO1",
      cohort: "matched_holdout",
      origin,
      targetTime: point.targetTime,
      horizon: horizon + 1,
      model: "ridge",
      actual: point.actual,
      prediction: point.ridge,
      baseline: point.baseline,
      lower: 111 + horizon,
      median: 148 + horizon,
      upper: 222 + horizon,
    },
  ]);
  const metric = (
    model: string,
    scope: string,
    mae: number,
    area?: string,
  ) => ({
    model,
    scope,
    ...(area ? { area } : {}),
    observations: 2,
    mae,
    rmse: mae + 1,
    mase: 0.8,
    baselineMae: 200,
    intervalCoverage: 0.5,
    meanIntervalWidth: 111,
    pinballLower: 2,
    pinballMedian: 3,
    pinballUpper: 4,
  });
  return {
    id,
    kind: "evaluation",
    title,
    createdAt,
    config: {
      areas: ["NO1"],
      models: ["seasonal_naive", "ridge"],
      horizon_hours: 2,
      interval_coverage: 0.8,
      weather_mode: "historical_only",
    },
    metadata: { task: "Synthetic household demand", unit: "kWh" },
    predictions,
    metrics: [
      metric("seasonal_naive", "overall", 200),
      metric("ridge", "overall", ridgeMae),
      metric("seasonal_naive", "area", 200, "NO1"),
      metric("ridge", "area", 900, "NO1"),
    ],
    failures: [],
  };
}

async function mockForecastApi(
  page: Page,
  options: { failBOnce?: boolean; failJobs?: boolean } = {},
) {
  let bRequests = 0;
  await page.route("**/api/forecasts/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/capabilities")) {
      await route.fulfill({ json: { customJobsEnabled: false } });
    } else if (path.endsWith("/results")) {
      await route.fulfill({
        json: {
          items: [
            summary("result-a", "Result A"),
            summary("result-b", "Result B"),
          ],
          total: 2,
        },
      });
    } else if (path.endsWith("/jobs")) {
      await route.fulfill(
        options.failJobs
          ? { status: 503, json: { detail: "Job history unavailable" } }
          : { json: { items: [], total: 0 } },
      );
    } else if (path.endsWith("/results/result-a")) {
      await route.fulfill({ json: result("result-a", "Result A", 120) });
    } else if (path.endsWith("/results/result-b")) {
      bRequests += 1;
      await route.fulfill(
        options.failBOnce && bRequests === 1
          ? {
              status: 503,
              json: { detail: "Result B temporarily unavailable" },
            }
          : { json: result("result-b", "Result B", 35) },
      );
    } else {
      await route.continue();
    }
  });
}

test("a failed result switch hides stale detail and retry restores the selected result", async ({
  page,
}) => {
  await mockForecastApi(page, { failBOnce: true });
  await page.goto("/forecasts?result=result-a");
  await expect(page.getByText("120 kWh", { exact: true })).toBeVisible();

  await page
    .getByRole("combobox", { name: "Prepared forecast result" })
    .click();
  await page.getByRole("option", { name: /Result B/ }).click();
  await expect(page).toHaveURL(/result=result-b/);
  const resultError = page.getByRole("alert").filter({
    hasText: "Result B temporarily unavailable",
  });
  await expect(resultError).toBeVisible();
  await expect(page.getByText("120 kWh", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("img", { name: /Result A NO1/ })).toHaveCount(0);
  await expect(page.locator(".analysis-chart .chart-export")).toHaveCount(0);

  await page.getByRole("button", { name: /retry/i }).click();
  await expect(page.getByText("35 kWh", { exact: true })).toBeVisible();
  await expect(resultError).toHaveCount(0);
  await expect(page.getByRole("img", { name: /Result B NO1/ })).toBeVisible();
  await expect(page.locator(".analysis-chart .chart-export")).toHaveCount(1);
});

test("saved results remain readable if job history fails in public mode", async ({
  page,
}) => {
  await mockForecastApi(page, { failJobs: true });
  await page.goto("/forecasts?result=result-a");
  await expect(
    page.getByRole("heading", { name: "Saved test summary" }),
  ).toBeVisible();
  await expect(page.getByText("120 kWh", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Experiment settings" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Run experiments locally" }),
  ).toBeVisible();
});

test("forecast data keeps each model's stored interval bounds distinct", async ({
  page,
}) => {
  await mockForecastApi(page);
  await page.goto("/forecasts?result=result-a");
  await expect(
    page.getByRole("heading", { name: "Saved test summary" }),
  ).toBeVisible();
  const intervalModel = page.getByRole("combobox", { name: "Interval model" });
  await expect(intervalModel).toHaveAttribute("data-value", "ridge");
  await intervalModel.click();
  await page.getByRole("option", { name: "Seasonal baseline" }).click();
  await expect(intervalModel).toHaveAttribute("data-value", "seasonal_naive");
  await intervalModel.click();
  await page.getByRole("option", { name: "Ridge" }).click();
  await page.getByText("View forecast data", { exact: true }).click();

  const table = page.getByRole("table").filter({ hasText: "Ridge" });
  await expect(table).toBeVisible();
  const ridge = table.getByRole("row").filter({ hasText: "Ridge" }).first();
  const baseline = table
    .getByRole("row")
    .filter({ hasText: "Seasonal baseline" })
    .first();
  await expect(ridge).toContainText("111");
  await expect(ridge).toContainText("222");
  await expect(baseline).toContainText("101");
  await expect(baseline).toContainText("202");
});

test("forecast tooltips and data tables stay within a mobile viewport and export a labeled PNG", async ({
  page,
}, testInfo) => {
  await mockForecastApi(page);
  await page.goto("/forecasts?result=result-a");
  const chart = page.getByRole("img", {
    name: "Result A NO1 matched_holdout forecast",
    exact: true,
  });
  await chart.click({ position: { x: 120, y: 160 } });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
    .toBeLessThanOrEqual(390);
  await page.getByText("View forecast data", { exact: true }).click();
  const table = page.getByRole("region", {
    name: "Forecast data table",
    exact: true,
  });
  await table.focus();
  await table.press("ArrowRight");
  await expect
    .poll(() => table.evaluate((element) => element.scrollLeft))
    .toBeGreaterThan(0);
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
    .toBeLessThanOrEqual(390);
  await page.getByRole("button", { name: "Export", exact: true }).click();
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", {
      name: "Download Result A NO1 matched_holdout forecast as PNG",
      exact: true,
    })
    .click();
  await (await download).saveAs(testInfo.outputPath("forecast-labeled.png"));
  await expect(chart).toBeVisible();
});

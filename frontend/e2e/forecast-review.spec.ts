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
  options: { failBOnce?: boolean; failJobs?: boolean; studyA?: boolean } = {},
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
      const saved = result("result-a", "Result A", 120);
      await route.fulfill({
        json: options.studyA
          ? {
              ...saved,
              metadata: {
                ...saved.metadata,
                studyProtocol: {
                  id: "synthetic-step-2",
                  label: "Synthetic Step 2 test",
                  evidenceStatus: "exploratory",
                },
              },
              reliability: {
                schemaVersion: 1,
                method: { supportRule: "Synthetic matched rows." },
                support: {
                  scheduledDates: 46,
                  observedDates: 44,
                  missingDates: ["2025-03-14T00:00:00Z"],
                  scheduledAreaOrigins: 230,
                  matchedAreaOrigins: 219,
                  excludedAreaOrigins: 11,
                  hourlyRowsPerModel: { ridge: 5256 },
                },
                models: [
                  {
                    model: "ridge",
                    overall: {
                      maeDeltaVsBaseline: -12.4,
                      bias: 3.2,
                      intervalCoverage: 0.74,
                      meanIntervalWidth: 88.1,
                    },
                    uncertainty: {
                      byBlockLength: [2, 4, 8].map((blockLengthDates) => ({
                        blockLengthDates,
                        intervals: {
                          maeDeltaVsBaseline: { lower: -20, upper: 5 },
                        },
                      })),
                    },
                    residualDependence: {
                      withinWindowLag1Hour: { pairs: 42, correlation: 0.35 },
                      byArea: [
                        { area: "NO1", withinWindowLag1Hour: { pairs: 20, correlation: 0.25 } },
                        { area: "NO2", withinWindowLag1Hour: { pairs: 22, correlation: 0.45 } },
                      ],
                    },
                  },
                ],
              },
            }
          : saved,
      });
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

test("exploratory reliability stays scoped to its fixed study cohort and older results omit it", async ({ page }) => {
  await mockForecastApi(page, { studyA: true });
  await page.goto("/forecasts?result=result-a");
  const panel = page.getByRole("region", { name: "Reliability comparison" });
  await expect(page.getByRole("heading", { name: "Reliability across dates" })).toBeVisible();
  await expect(panel).toContainText("-12.4");
  await expect(panel).toContainText("2 dates: -20 to +5");
  await expect(panel).toContainText("74%");
  await expect(page.getByText("219", { exact: true })).toBeVisible();
  await expect(page.getByText(/Missing dates: 2025-03-14/)).toBeVisible();
  await page.getByText("Support and residual dependence").click();
  await expect(page.getByText(/pools all areas and matched dates/)).toBeVisible();
  const diagnostics = page.getByRole("region", { name: "Residual dependence diagnostics" });
  await expect(diagnostics).toContainText("0.25");
  await page.getByRole("combobox", { name: "Residual area" }).selectOption("NO2");
  await expect(diagnostics).toContainText("0.45");
  await expect(diagnostics).not.toContainText("0.25");
  await page.getByRole("combobox", { name: "Prepared forecast result" }).click();
  await page.getByRole("option", { name: /Result B/ }).click();
  await expect(page.getByRole("heading", { name: "Reliability across dates" })).toHaveCount(0);
});

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
    page.getByRole("heading", { name: "All-area benchmark" }),
  ).toBeVisible();
  await expect(page.getByText("120 kWh", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Experiment settings" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Methods & local setup" }),
  ).toHaveAttribute("href", "/methods#local-experiments");
});

test("forecast data keeps each model's stored interval bounds distinct", async ({
  page,
}) => {
  await mockForecastApi(page);
  await page.goto("/forecasts?result=result-a");
  await expect(
    page.getByRole("heading", { name: "All-area benchmark" }),
  ).toBeVisible();
  const intervalModel = page.getByRole("combobox", { name: "Interval model" });
  await expect(intervalModel).toHaveAttribute("data-value", "ridge");
  await intervalModel.click();
  await page.getByRole("option", { name: "Seasonal baseline" }).click();
  await expect(intervalModel).toHaveAttribute("data-value", "seasonal_naive");
  await intervalModel.click();
  await page.getByRole("option", { name: "Ridge" }).click();
  await page.getByText("View forecast data", { exact: true }).click();

  const table = page.getByRole("region", { name: "Forecast data table", exact: true }).getByRole("table");
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

import { expect, test } from "@playwright/test";

function studyArea(area: string) {
  const score = { mae: 12, rmse: 16, bias: 1, count: 100 };
  return {
    area,
    status: "ok",
    selectedModel: "linear",
    referenceTemperature: 5,
    curve: [
      { temperature: 0, effect: 20, lower: 12, upper: 28, lower336: 10, upper336: 30, supported: true, count: 80 },
      { temperature: 5, effect: 0, lower: 0, upper: 0, lower336: 0, upper336: 0, supported: true, count: 100 },
      { temperature: 10, effect: -20, lower: -28, upper: -12, lower336: -30, upper336: -10, supported: true, count: 70 },
    ],
    support: { min: 0, max: 10, bins: [{ temperature: 0, count: 80 }, { temperature: 5, count: 100 }, { temperature: 10, count: 70 }], byMonth: [{ month: 1, count: 80, min: 0, max: 10 }] },
    models: [
      { model: "calendar", label: "Calendar", validation: { ...score, mae: 15 }, test: { ...score, mae: 16 }, parameters: {} },
      { model: "linear", label: "Linear", validation: score, test: score, parameters: {} },
      { model: "spline", label: "Cubic spline", validation: { ...score, mae: 13 }, test: { ...score, mae: 14 }, parameters: {} },
    ],
    splits: {
      train: { start: "2021-01-01T00:00:00+00:00", end: "2024-01-01T00:00:00+00:00", expectedHours: 26000, observedHours: 25800 },
      validation: { start: "2024-01-01T00:00:00+00:00", end: "2025-01-01T00:00:00+00:00", expectedHours: 8784, observedHours: 8700 },
      test: { start: "2025-01-01T00:00:00+00:00", end: "2026-01-01T00:00:00+00:00", expectedHours: 8760, observedHours: 8600 },
    },
    residuals: { acf: [{ lagHours: 1, correlation: 0.2, pairs: 99 }], byHour: [{ hour: 0, mean: 1, count: 100 }], byMonth: [{ month: 1, mean: 1, count: 100 }] },
    sensitivity: { maxCurveDifference: 3, harmonics: 4, notes: "Four rather than two annual terms." },
    metadata: {},
  };
}

const study = {
  schemaVersion: 1,
  id: "ui-fixture",
  createdAt: "2026-09-21T00:00:00Z",
  dataMode: "fixture",
  protocol: {},
  areas: [studyArea("NO1"), studyArea("NO2"), ...["NO3", "NO4", "NO5"].map((area) => ({ area, status: "unavailable", reason: "Missing paired hours" }))],
  metadata: {},
};

test("saved demand sensitivity keeps its own area and browser history", async ({ page }) => {
  await page.route("**/api/diagnostics/sensitivity", (route) => route.fulfill({ json: study }));
  await page.route("**/api/diagnostics/sensitivity/artifact", (route) => route.fulfill({ status: 200, body: JSON.stringify(study), headers: { "content-type": "application/json", "content-disposition": "attachment; filename=demand-sensitivity.json" } }));
  await page.goto("/diagnostics?view=sensitivity&area=NO1&start=2026-08-01&end=2026-08-28");
  await expect(page.getByRole("combobox", { name: "Analysis" })).toHaveAttribute("data-value", "sensitivity");
  await expect(page.getByRole("heading", { name: "Temperature & demand" })).toBeVisible();
  await page.getByText("Model comparison, coverage & residual checks", { exact: true }).click();
  await expect(page.getByText("2021-01-01–2024-01-01 UTC")).toBeVisible();
  await expect(page.getByRole("button", { name: "Run analysis" })).toHaveCount(0);
  await expect(page.getByText("Energy kind")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /date range/i })).toHaveCount(0);

  await page.getByRole("combobox", { name: "Sensitivity price area" }).click();
  await page.getByRole("option", { name: "NO2 · Southern Norway" }).click();
  await expect(page).toHaveURL(/view=sensitivity&area=NO2/);
  await page.goBack();
  await expect(page.getByRole("combobox", { name: "Sensitivity price area" })).toContainText("NO1");

  await page.getByRole("combobox", { name: "Analysis" }).click();
  await page.getByRole("option", { name: "Unusual observations" }).click();
  await expect(page.getByRole("combobox", { name: "Analysis" })).toHaveAttribute("data-value", "quality");
  await page.getByRole("combobox", { name: "Analysis" }).click();
  await page.getByRole("option", { name: "Demand sensitivity" }).click();
  await expect(page.getByRole("combobox", { name: "Analysis" })).toHaveAttribute("data-value", "sensitivity");

  await page.getByRole("button", { name: "Export study" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Complete artifact JSON" }).click();
  expect((await download).suggestedFilename()).toBe("demand-sensitivity.json");
});

test("transient sensitivity failure can be retried", async ({ page }) => {
  let requests = 0;
  await page.route("**/api/diagnostics/sensitivity", (route) => {
    requests += 1;
    return requests === 1
      ? route.fulfill({ status: 503, json: { detail: "Temporary study outage" } })
      : route.fulfill({ json: study });
  });
  await page.goto("/diagnostics?view=sensitivity&area=NO1");
  await expect(page.getByRole("alert").filter({ hasText: "Couldn’t load this study" })).toContainText("Temporary study outage");
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("heading", { name: "Temperature & demand" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Adjusted temperature response" })).toBeVisible();
});

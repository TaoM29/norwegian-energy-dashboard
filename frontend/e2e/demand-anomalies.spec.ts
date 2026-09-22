import { expect, test, type Page } from "@playwright/test";

const start = "2025-01-08T00:00:00+00:00";
const candidateId = (rank: number) => `NO1-${start}-${rank % 2 ? "high" : "low"}-${rank}`;
const candidates = Array.from({ length: 20 }, (_, index) => ({
  id: candidateId(index + 1), start, endExclusive: "2025-01-08T03:00:00+00:00",
  peakTime: new Date(Date.parse(start) + index * 3_600_000).toISOString(),
  direction: index % 2 ? "low" as const : "high" as const,
  hours: index + 1, peakScore: 5 - index / 10,
  peakActual: 150 + index, peakExpected: 100 + index,
  peakTemperature: 1 + index / 10,
}));
const contextRows = [0, 1, 2].map((hour) => ({
  time: new Date(Date.parse(start) + hour * 3_600_000).toISOString(),
  actual: hour === 2 ? null : 150 + hour,
  temperature: 1 + hour,
  rawExpected: hour === 2 ? null : 99 + hour,
  expected: hour === 2 ? null : 100 + hour,
  lower: hour === 2 ? null : 80 + hour,
  upper: hour === 2 ? null : 120 + hour,
  residual: hour === 2 ? null : 50,
  score: hour === 2 ? null : 2,
  flagged: hour !== 2,
  status: hour === 2 ? "missing_demand" : "ok",
  localDate: "2025-01-08", localHour: hour + 1,
}));
const peerRows = [0, 1].map((hour) => ({
  time: new Date(Date.parse("2024-01-08T00:00:00Z") + hour * 3_600_000).toISOString(),
  localHour: hour + 1, actual: 110 + hour, temperature: 2 + hour,
}));

function response(area: string, requestedCandidate: string) {
  const unavailable = area === "NO2";
  const chosen = candidates.find((item) => item.id === requestedCandidate) || candidates[0];
  const peers = chosen.id === candidates[1].id
    ? { status: "unavailable", reason: "target Oslo date has 23 or 25 hours due to daylight saving time", excludedDstDays: 2, days: [] }
    : { status: "available", targetDate: "2025-01-08", targetHours: 24,
      targetRows: peerRows, excludedDstDays: 2,
      days: [{ date: "2024-01-08", temperatureDifference: 0.5, seasonDistance: 0, rows: peerRows }],
    };
  return {
    schemaVersion: 1, id: "fixture-demand-anomalies", createdAt: "2026-09-22T00:00:00Z",
    dataMode: "fixture", protocol: { purpose: "Synthetic example" }, metadata: { sourceLabel: "Synthetic test fixture" },
    areas: [
      { area: "NO1", status: "ok", summary: { episodes: 24 } },
      { area: "NO2", status: "unavailable", reason: "Insufficient observed pairs" },
    ],
    selectedArea: unavailable ? { area, status: "unavailable", reason: "Insufficient observed pairs", candidates: [] } : {
      area, status: "ok", selectedModel: "spline4", candidateLimit: 20, totalCandidates: 24,
      selection: { models: [
        { model: "calendar", validation: { mae: 20, rmse: 25, bias: 2, count: 200 } },
        { model: "spline4", validation: { mae: 15, rmse: 20, bias: 1, count: 200 } },
      ], selectedSplineKnots: 4, rule: "Validation MAE; complexity needs improvement." },
      splits: { train: { start: "2021-01-01T00:00:00Z", endExclusive: "2023-01-01T00:00:00Z", completeHours: 17300 },
        validation: { start: "2023-01-01T00:00:00Z", endExclusive: "2024-01-01T00:00:00Z", completeHours: 8650 },
        calibration: { start: "2024-01-01T00:00:00Z", endExclusive: "2025-01-01T00:00:00Z", completeHours: 8700 },
        test: { start: "2025-01-01T00:00:00Z", endExclusive: "2026-01-01T00:00:00Z", completeHours: 8500 } },
      calibration: { medianCorrection: 1, lowerResidual: -20, upperResidual: 20,
        lowerWidth: 21, upperWidth: 19, observations: 8700, distinctDates: 366,
        tailFraction: 0.01, groupSupport: {
          season: [{ season: "winter", hours: 2000, scoredHours: 1990, flaggedHours: 15, flagRate: 15 / 1990 }],
          dayType: [{ dayType: "weekday", hours: 6000, scoredHours: 5900, flaggedHours: 43, flagRate: 43 / 5900 }],
        } },
      coverage: { train: { expectedHours: 17520, completeHours: 17300 }, validation: { expectedHours: 8760, completeHours: 8650 },
        calibration: { expectedHours: 8784, scoredHours: 8700 },
        test: { expectedHours: 8760, scoredHours: 8500, missingHours: 200, unsupportedHours: 60,
          statusCounts: { ok: 8500, missing_demand: 100, missing_temperature: 80, missing_both: 20, unsupported_temperature: 60 } } },
      summary: { expectedHours: 8760, scoredHours: 8500, flaggedHours: 75, flagRate: 75 / 8500, episodes: 24 },
      diagnostics: {}, metadata: { featureColumns: ["intercept", "oslo_hour_1", "temperature_spline_basis_0"] },
      candidates,
    },
    selection: { candidate: unavailable ? null : chosen, rows: unavailable ? [] : contextRows, peers: unavailable ? {} : peers },
  };
}

async function mockApi(page: Page) {
  await page.route("**/api/diagnostics/demand-anomalies**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/artifact")) return route.fulfill({
      status: 200, body: JSON.stringify(response("NO1", "")),
      headers: { "content-type": "application/json", "content-disposition": "attachment; filename=demand-anomalies.json" },
    });
    const area = url.searchParams.get("area") || "NO1";
    const requested = url.searchParams.get("candidate") || "";
    if (requested && !candidates.some((item) => item.id === requested)) {
      return route.fulfill({ status: 404, json: { detail: "The requested candidate is not in the saved review list." } });
    }
    return route.fulfill({ json: response(area, requested) });
  });
}

test("saved demand anomalies keep area and candidate URL state and distinguish coverage", async ({ page }) => {
  await mockApi(page);
  await page.goto("/diagnostics?view=demand_anomalies&area=NO1");
  await expect(page.getByRole("combobox", { name: "Analysis" })).toHaveAttribute("data-value", "demand_anomalies");
  await expect(page.getByRole("heading", { name: "Unusual household demand" })).toBeVisible();
  await expect(page.getByText("Fixture demonstration")).toBeVisible();
  await expect(page.locator(".demand-anomalies-summary").getByText("8,500", { exact: true })).toBeVisible();
  await expect(page.getByText("Unlabeled observational flags")).toBeVisible();
  await expect(page.getByText(/Top 20 of 24 saved episodes/)).toBeVisible();
  const ranking = page.getByRole("region", { name: "Ranked demand anomaly candidates" });
  await expect(ranking.getByRole("row")).toHaveCount(21);
  await ranking.getByRole("button", { name: /^2\. 8 Jan 2025/ }).click();
  await expect(page).toHaveURL(/candidate=NO1-/);
  const peerDays = page.locator("details.study-details").filter({ hasText: "Comparable observed days" });
  await peerDays.locator(":scope > summary").click();
  await expect(page.getByText(/target Oslo date has 23 or 25 hours/)).toBeVisible();
  await page.goBack();
  if (!(await peerDays.evaluate((element) => (element as HTMLDetailsElement).open))) {
    await peerDays.locator(":scope > summary").click();
  }
  await expect(page.getByRole("region", { name: "Comparable peer days" })).toContainText("2024-01-08");
  await page.getByText("Hourly peer and selected-day observations").click();
  await expect(page.getByRole("region", { name: "2024-01-08 hourly observations" }).getByRole("cell", { name: "110", exact: true })).toBeVisible();
  await expect(page.getByText(/not a prediction or confidence interval/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Show reference window" })).toHaveCount(0);
  await page.getByText("Hourly context and coverage status").click();
  await expect(page.getByRole("region", { name: "Selected anomaly hourly context" })).toContainText("missing demand");
  await expect(page.getByRole("region", { name: "Selected anomaly hourly context" })).toContainText("Flagged");
  await expect(page.getByText("Missing demand only")).toBeVisible();
  await expect(page.getByText("Unsupported temperature")).toBeVisible();
  await page.getByText("Model selection, calendar thresholds and study periods").click();
  await expect(page.getByText(/expected value adds a \+1 kWh median correction/)).toBeVisible();
  await expect(page.getByText(/extends -21 kWh below and \+19 kWh above/)).toBeVisible();
  await expect(page.getByRole("region", { name: "season calibration support" })).toContainText("winter");
  await expect(page.getByRole("region", { name: "Expected-demand model validation" })).toContainText("spline4");
  const periods = page.getByRole("region", { name: "Demand anomaly study periods" });
  await expect(periods.getByRole("row", { name: /train/ })).toContainText("2023-01-01T00:00:00Z");
  await expect(periods.getByRole("row", { name: /train/ })).toContainText("17,300");
  await page.getByRole("button", { name: "Export anomaly study" }).click();
  await expect(page.getByRole("link", { name: "Complete artifact JSON" })).toHaveAttribute("href", "/api/diagnostics/demand-anomalies/artifact");
  await page.getByRole("combobox", { name: "Demand anomalies price area" }).click();
  await page.getByRole("option", { name: "NO2 · Southern Norway" }).click();
  await expect(page).toHaveURL(/view=demand_anomalies&area=NO2/);
  await expect(page.getByText("Insufficient observed pairs")).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("combobox", { name: "Demand anomalies price area" })).toContainText("NO1");
  await page.getByRole("combobox", { name: "Analysis" }).click();
  await page.getByRole("option", { name: "Demand sensitivity" }).click();
  await expect(page.getByRole("combobox", { name: "Analysis" })).toHaveAttribute("data-value", "sensitivity");
  await page.getByRole("combobox", { name: "Analysis" }).click();
  await page.getByRole("option", { name: "Unusual observations" }).click();
  await expect(page.getByRole("combobox", { name: "Analysis" })).toHaveAttribute("data-value", "quality");
});

test("invalid candidate recovers and mobile tables remain scrollable in both themes", async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/diagnostics?view=demand_anomalies&area=NO1&candidate=unknown");
  await expect(page.getByRole("alert").filter({ hasText: "Couldn’t load this study" })).toContainText("The requested candidate is not in the saved review list.");
  await page.getByRole("button", { name: "Clear selected candidate" }).click();
  await expect(page.getByRole("region", { name: "Ranked demand anomaly candidates" })).toBeVisible();
  for (const theme of ["Light", "Dark"]) {
    await page.getByRole("button", { name: theme, exact: true }).click();
    const table = page.getByRole("region", { name: "Ranked demand anomaly candidates" });
    await table.focus();
    await table.press("ArrowRight");
    await expect.poll(() => table.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  }
});

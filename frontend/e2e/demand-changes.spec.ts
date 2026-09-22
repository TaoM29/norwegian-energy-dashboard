import { expect, test, type Page } from "@playwright/test";

const first = Date.parse("2025-01-01T00:00:00Z");
const date = (index: number) => new Date(first + index * 86_400_000).toISOString().slice(0, 10);
const dailyRows = Array.from({ length: 90 }, (_, index) => ({
  date: date(index), period: "test", actual: index === 10 ? null : 100 + (index >= 45 ? 8 : 0),
  expected: index === 10 ? null : 100, residual: index === 10 ? null : index >= 45 ? 8 : 0,
  okHours: index === 10 ? 23 : 24, expectedHours: 24,
  statusCounts: index === 10 ? { ok: 23, missing_demand: 1 } : { ok: 24 }, complete: index !== 10,
}));
const segment = (start: number, end: number, residual: number) => ({
  start: date(start), endExclusive: date(end), days: end - start,
  meanActual: 100 + residual, meanExpected: 100, meanResidual: residual,
  medianResidual: residual, q1Residual: residual, q3Residual: residual,
  residualDistribution: Array.from({ length: end - start }, () => residual),
});

function savedStudy(detected = true) {
  return {
    schemaVersion: 1, id: "fixture-demand-changes", createdAt: "2026-09-22T00:00:00Z",
    dataMode: "fixture", area: "NO1", status: "ok",
    protocol: { baseline: "frozen Step 5 calendar-weather model", minSegmentDays: 28, alpha: 0.05 },
    coverage: {
      calibration: { expectedDays: 366, completeDays: 366, incompleteDays: 0, expectedHours: 8784, okHours: 8784, statusCounts: { ok: 8784 } },
      test: { expectedDays: 90, completeDays: 89, incompleteDays: 1, expectedHours: 2160, okHours: 2159,
        statusCounts: { ok: 2159, missing_demand: 1 } },
    },
    dailyRows,
    primary: { status: "ok", detected, score: 4.2, pValue: detected ? 0.02 : 0.22,
      thresholdApprox95: 3.5, calibrationScaleKwh: 5.1, eligibleSplits: 34,
      testRuns: [{ startIndex: 11, endExclusiveIndex: 90, days: 79 }], bootstrapMaxima: [2.5, 3.1],
      candidate: { date: date(45), before: segment(11, 45, 0), after: segment(45, 90, 8),
        deltaResidualKwh: 8, standardizedDelta: 1.57 },
    },
    sensitivities: [{ id: "gap-check", label: "Gap check", detected: false, score: 2.1,
      pValue: 0.19, thresholdApprox95: 3.5, candidateDate: date(45), deltaResidualKwh: 7.3, eligibleSplits: 34 }],
    controlledValidation: { specification: { replications: 200 }, summary: [
      { rho: 0.4, scenario: "no-change", replications: 200, detections: 12, detectionRate: 0.06, falseAlarmRate: 0.06 },
      { rho: 0.8, scenario: "no-change", replications: 200, detections: 41, detectionRate: 0.205, falseAlarmRate: 0.205 },
    ] },
    metadata: { sourceLabel: "Synthetic test fixture" },
  };
}

async function mockStudy(page: Page, detected = true) {
  await page.route("**/api/diagnostics/demand-changes**", async (route) => {
    if (new URL(route.request().url()).pathname.endsWith("/artifact")) return route.fulfill({
      status: 200, body: JSON.stringify(savedStudy(detected)),
      headers: { "content-type": "application/json", "content-disposition": "attachment; filename=demand-changes.json" },
    });
    return route.fulfill({ json: savedStudy(detected) });
  });
}

test("saved change view shows one retrospective split and keeps detail optional", async ({ page }) => {
  await mockStudy(page);
  await page.goto("/diagnostics?view=demand_changes&area=NO3&start=2026-01-01");
  await expect(page.getByRole("combobox", { name: "Analysis" })).toHaveAttribute("data-value", "demand_changes");
  await expect(page.getByRole("heading", { name: "Persistent demand changes" })).toBeVisible();
  await expect(page.getByText("Fixture demonstration")).toBeVisible();
  await expect(page.getByText("NO1 · 2025-01-01–2025-03-31 UTC")).toBeVisible();
  await expect(page.getByText("89 of 90 complete UTC days")).toBeVisible();
  await expect(page.getByText("Strongest exploratory split near 15 Feb 2025")).toBeVisible();
  await expect(page.getByText("+8 kWh", { exact: true })).toBeVisible();
  await expect(page.getByText(/41 of 200 runs were flagged \(20.5%\)/)).toBeVisible();
  await expect(page.getByRole("img", { name: /NO1 2025 daily mean household-demand residuals/ })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Price area" })).toHaveCount(0);
  await page.getByRole("button", { name: "Before & after" }).click();
  await expect(page.getByRole("img", { name: /before and after distributions/ })).toBeVisible();
  await expect(page.getByText(/Percentages account for unequal period lengths/)).toBeVisible();
  await expect(page.getByText(/The dashed split line is/)).toHaveCount(0);
  await page.getByText("Before and after estimates").click();
  await expect(page.getByRole("region", { name: "Demand-change before and after estimates" })).toContainText("2025-02-15");
  await page.getByText("Daily values and coverage").click();
  await expect(page.getByRole("region", { name: "Saved daily demand-change values" })).toContainText("Incomplete");
  await page.getByText("Detection policy and validation").click();
  await expect(page.getByText(/maximum over every eligible split in each bootstrap draw/)).toBeVisible();
  await page.getByRole("button", { name: "Export demand-change study" }).click();
  await expect(page.getByRole("link", { name: "Complete artifact JSON" })).toHaveAttribute("href", "/api/diagnostics/demand-changes/artifact");
});

test("below-threshold split is labeled unconfirmed and mobile view stays within viewport", async ({ page }) => {
  await mockStudy(page, false);
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/diagnostics?view=demand_changes");
  await expect(page.getByText("Best split near 15 Feb 2025 remains unconfirmed")).toBeVisible();
  await expect(page.getByText(/did not exceed the saved bootstrap threshold/)).toBeVisible();
  await page.getByRole("button", { name: "Before & after" }).click();
  await expect(page.getByRole("img", { name: /before and after distributions/ })).toBeVisible();
  const details = page.locator("summary").filter({ hasText: "Daily values and coverage" });
  await details.focus();
  await details.press("Enter");
  await expect(page.getByRole("region", { name: "Saved daily demand-change values" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
});

test("missing saved study offers retry and does not show stale findings", async ({ page }) => {
  let available = false;
  await page.route("**/api/diagnostics/demand-changes", async (route) => {
    if (!available) return route.fulfill({ status: 503, json: { detail: "Saved study is not available yet." } });
    return route.fulfill({ json: savedStudy() });
  });
  await page.goto("/diagnostics?view=demand_changes");
  await expect(page.getByRole("alert").filter({ hasText: "Couldn’t load this study" })).toContainText("Saved study is not available yet.");
  await expect(page.getByText("Strongest exploratory split near 15 Feb 2025")).toHaveCount(0);
  available = true;
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("Strongest exploratory split near 15 Feb 2025")).toBeVisible();
});

test("an unavailable saved evaluation explains why no finding is shown", async ({ page }) => {
  await page.route("**/api/diagnostics/demand-changes", (route) => route.fulfill({ json: {
    schemaVersion: 1, id: "unavailable-study", createdAt: "2026-09-22T00:00:00Z",
    dataMode: "fixture", area: "NO1", status: "unavailable",
    reason: "Insufficient complete calibration blocks", protocol: {}, metadata: {},
  } }));
  await page.goto("/diagnostics?view=demand_changes");
  await expect(page.getByText("Saved study unavailable")).toBeVisible();
  await expect(page.getByText("Insufficient complete calibration blocks")).toBeVisible();
  await expect(page.getByRole("img", { name: /NO1 2025 daily mean/ })).toHaveCount(0);
});

test("loading resolves to an inconclusive saved scan when no split is eligible", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const base = savedStudy();
  await page.route("**/api/diagnostics/demand-changes", async (route) => {
    await gate;
    return route.fulfill({ json: { ...base, primary: {
      ...base.primary, status: "insufficient_data", detected: false, score: null,
      pValue: null, thresholdApprox95: null, candidate: null, eligibleSplits: 0,
    } } });
  });
  await page.goto("/diagnostics?view=demand_changes");
  await expect(page.getByRole("status").filter({ hasText: "Loading saved demand-change study" })).toBeVisible();
  release();
  await expect(page.getByText("This study is inconclusive")).toBeVisible();
  await expect(page.getByText(/No split line or before\/after estimate is shown/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Before & after" })).toHaveCount(0);
});

test("prepared offline fixture reaches the API and the saved-study view", async ({ page, request }) => {
  const response = await request.get("/api/diagnostics/demand-changes");
  expect(response.ok()).toBeTruthy();
  const study = await response.json();
  expect(study.schemaVersion).toBe(1);
  expect(study.area).toBe("NO1");
  expect(study.dataMode).toBe("fixture");
  expect(study.status).toBe("ok");
  const testRows = study.dailyRows.filter((row: { period: string }) => row.period === "test");
  expect(testRows).toHaveLength(study.coverage.test.expectedDays);
  expect(testRows.length).toBeGreaterThan(56);
  await page.goto("/diagnostics?view=demand_changes");
  await expect(page.getByText("Fixture demonstration")).toBeVisible();
  await expect(page.getByRole("img", { name: /NO1 2025 daily mean household-demand residuals/ })).toBeVisible();
  await page.getByRole("button", { name: "Export demand-change study" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Complete artifact JSON" }).click();
  expect((await download).suggestedFilename()).toBe("demand-changes.json");
});

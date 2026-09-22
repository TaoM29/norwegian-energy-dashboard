import { expect, test, type Page } from "@playwright/test";

const first = "2025-01-01T00:00:00Z";
const second = "2025-01-01T01:00:00Z";

async function mockPeaks(page: Page) {
  await page.route("**/api/explore/demand-peaks?**", async (route) => {
    const url = new URL(route.request().url());
    await route.fulfill({ json: {
      query: { area: url.searchParams.get("area"), start: url.searchParams.get("start"), end: url.searchParams.get("end"), kind: "consumption", group: "household", interval: "[start,end)" },
      dataMode: "fixture", unit: "kWh", metadata: { provenance: { source: "test" } }, area: url.searchParams.get("area"),
      coverage: { expectedHours: 3, observedHours: 2, excludedHours: 1, validRampPairs: 1, expectedRampPairs: 2 },
      summary: { meanKwh: 120, peak: { time: second, valueKwh: 140, tieCount: 1 }, largestRise: { previousTime: first, time: second, changeKwh: 40, tieCount: 1 }, largestFall: null },
      duration: [{ valueKwh: 140, hoursAtOrAbove: 1, percentAtOrAbove: 50 }, { valueKwh: 100, hoursAtOrAbove: 2, percentAtOrAbove: 100 }],
      hourly: [{ time: first, valueKwh: 100, changeKwh: null }, { time: second, valueKwh: 140, changeKwh: 40 }, { time: "2025-01-01T02:00:00Z", valueKwh: null, changeKwh: null }],
      calculation: { ramp: "Consecutive UTC observations only" },
    } });
  });
  await page.route("**/api/regional/demand-peaks?**", async (route) => {
    const url = new URL(route.request().url());
    await route.fulfill({ json: {
      query: { start: url.searchParams.get("start"), end: url.searchParams.get("end"), kind: "consumption", group: "household", interval: "[start,end)" },
      dataMode: "fixture", unit: "kWh", metadata: { provenance: { source: "test" } },
      coverage: { expectedHours: 3, matchedHours: 2, excludedHours: 1, byArea: ["NO1", "NO2", "NO3", "NO4", "NO5"].map((area) => ({ area, observedHours: 2, excludedHours: 1 })) },
      areas: ["NO1", "NO2", "NO3", "NO4", "NO5"].map((area, index) => ({ area, meanKwh: 110 + index * 10, peak: { time: second, valueKwh: 120 + index * 10, tieCount: 1 }, atCoincidentPeakKwh: 120 + index * 10 })),
      coincidentPeak: { time: second, valueKwh: 700, tieCount: 1 }, sumIndividualPeaksKwh: 700, coincidenceFactor: 1,
      correlations: [{ areaA: "NO1", areaB: "NO2", r: 0.9, hours: 2 }],
      hourly: [{ time: first, NO1: 100, NO2: 110, NO3: 120, NO4: 130, NO5: 140 }, { time: second, NO1: 120, NO2: 130, NO3: 140, NO4: 150, NO5: 160 }, { time: "2025-01-01T02:00:00Z", NO1: null, NO2: null, NO3: null, NO4: null, NO5: null }],
      calculation: { matching: "Common valid UTC hours" },
    } });
  });
}

test("Explore peaks use the selected area and inclusive dates with chart modes and method details", async ({ page }, testInfo) => {
  await mockPeaks(page);
  await page.goto("/explore?view=peaks&area=NO2&start=2025-01-01&end=2025-01-03");
  await expect(page.getByRole("heading", { name: "Peaks & rapid changes" })).toBeVisible();
  await expect(page.getByText("Synthetic fixture example")).toBeVisible();
  await expect(page.getByText("140 kWh")).toBeVisible();
  await expect(page.getByRole("img", { name: /NO2 household demand load duration/ })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("explore-peaks-desktop.png"), animations: "disabled", fullPage: true });
  await page.getByRole("combobox", { name: "Peak demand chart" }).click();
  await page.getByRole("option", { name: "Hourly changes" }).click();
  await expect(page.getByRole("img", { name: /NO2 household demand hourly changes/ })).toBeVisible();
  await page.getByRole("button", { name: "Coverage & method" }).click();
  await expect(page.getByRole("dialog", { name: "Coverage & method" })).toContainText("Changes require consecutive observed UTC hours");
  await page.getByRole("button", { name: "Close Coverage & method" }).click();
  await page.getByRole("button", { name: /^Date range:/ }).click();
  await page.getByRole("dialog", { name: "Choose date range" }).getByLabel("End date", { exact: true }).fill("2025-01-04");
  await page.getByRole("button", { name: "Use dates" }).click();
  const nextQuery = page.waitForRequest((request) => request.url().includes("/api/explore/demand-peaks?") && request.url().includes("end=2025-01-05"));
  await page.getByRole("button", { name: "Apply view" }).click();
  await nextQuery;
  await expect(page).toHaveURL(/end=2025-01-04/);
  await expect(page.getByRole("img", { name: /NO2 household demand/ })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/end=2025-01-03/);
});

test("Regional peaks show matched coverage and remain usable on mobile in both themes", async ({ page }, testInfo) => {
  await mockPeaks(page);
  await page.setViewportSize({ width: 390, height: 844 });
  const firstQuery = page.waitForRequest((request) => request.url().includes("/api/regional/demand-peaks?") && request.url().includes("end=2025-01-04"));
  await page.goto("/regional?mode=peaks&start=2025-01-01&end=2025-01-03");
  await firstQuery;
  await expect(page.getByRole("tab", { name: "Demand peaks" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "Regional peak alignment" })).toBeVisible();
  await expect(page.getByText("2 / 3 hours matched across all areas")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("regional-peaks-mobile.png"), animations: "disabled", fullPage: true });
  await page.getByRole("combobox", { name: "Regional demand scale" }).click();
  await page.getByRole("option", { name: "Area mean · %" }).click();
  await expect(page.getByRole("img", { name: /relative to area mean/ })).toBeVisible();
  await page.getByText("Area peaks", { exact: true }).click();
  await expect(page.getByRole("region", { name: "Area peak comparison" }).getByRole("row")).toHaveCount(6);
  await page.getByRole("button", { name: "Coverage & method" }).click();
  await expect(page.getByRole("dialog", { name: "Coverage & method" })).toContainText("1 unmatched hour excluded");
  await page.getByRole("button", { name: "Close Coverage & method" }).click();
  for (const theme of ["Light", "Dark"]) {
    await page.getByRole("button", { name: theme, exact: true }).click();
    await expect(page.getByRole("img", { name: /relative to area mean/ })).toBeVisible();
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width).toBeLessThanOrEqual(395);
  }
  await page.getByRole("tab", { name: "Demand peaks" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Snow model" })).toHaveAttribute("aria-selected", "true");
  await page.goBack();
  await expect(page.getByRole("tab", { name: "Demand peaks" })).toHaveAttribute("aria-selected", "true");
});

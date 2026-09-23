import { expect, test, type Page } from "@playwright/test";

const profileHours = Array.from({ length: 24 }, (_, hour) => ({ hour, medianKwh: 100 + hour, p10Kwh: null, p90Kwh: null }));
const normalizedHours = Array.from({ length: 24 }, (_, hour) => ({ hour, medianPercentDailyMean: 90 + hour, p10PercentDailyMean: null, p90PercentDailyMean: null }));
const weekdayHours = Array.from({ length: 24 }, (_, hour) => ({ timeUtc: new Date(Date.UTC(2025, 9, 24, hour - 2)).toISOString().replace(".000Z", "Z"), timeOslo: `2025-10-24T${String(hour).padStart(2, "0")}:00:00+02:00`, localHour: hour, valueKwh: 100 + hour }));
const repeatedHours = [
  { timeUtc: "2025-10-26T00:00:00Z", timeOslo: "2025-10-26T02:00:00+02:00", localHour: 2, valueKwh: 100 },
  { timeUtc: "2025-10-26T01:00:00Z", timeOslo: "2025-10-26T02:00:00+01:00", localHour: 2, valueKwh: 110 },
];

async function mockProfiles(page: Page, empty = false) {
  await page.route("**/api/explore/demand-profiles?**", async (route) => {
    const url = new URL(route.request().url());
    const area = url.searchParams.get("area");
    await route.fulfill({ json: {
      query: { area, start: url.searchParams.get("start"), end: url.searchParams.get("end"), kind: "consumption", group: "household", interval: "[start,end)" },
      dataMode: "fixture", unit: "kWh", timezone: "Europe/Oslo", metadata: { provenance: { source: "test" } }, calculation: { localDay: "Europe/Oslo" },
      coverage: { expectedHours: 96, observedHours: 49, excludedHours: 47, missingHours: 1, badQualityHours: 0, nonfiniteOrNegativeHours: 0, expectedDays: 3, touchedDays: 4, profileEligibleDays: empty ? 0 : 1, boundaryExcludedDays: 2, dstExcludedDays: 1, incompleteExcludedDays: 0, zeroMeanDays: 0, normalizedEligibleDays: empty ? 0 : 1 },
      groups: [
        ["dayType", "weekday"], ["dayType", "weekend"], ["season", "SON"],
      ].map(([groupType, group]) => ({ groupType, group, actualDayCount: empty ? 0 : 1, normalizedDayCount: empty ? 0 : 1,
        actual: empty ? profileHours.map((row) => ({ ...row, medianKwh: null, p10Kwh: null, p90Kwh: null })) : profileHours,
        normalized: empty ? normalizedHours.map((row) => ({ ...row, medianPercentDailyMean: null, p10PercentDailyMean: null, p90PercentDailyMean: null })) : normalizedHours,
        representative: empty ? null : { date: "2025-10-24", squaredDistance: 0 },
      })),
      days: empty ? [] : [
        { date: "2025-10-24", dayType: "weekday", season: "SON", expectedHours: 24, selectedHours: 24, validHours: 24, profileEligible: true, normalizedEligible: true, exclusionReasons: [], meanKwh: 111.5, totalKwh: 2676, hours: weekdayHours },
        { date: "2025-10-26", dayType: "weekend", season: "SON", expectedHours: 25, selectedHours: 25, validHours: 25, profileEligible: false, normalizedEligible: false, exclusionReasons: ["dst25HourDay"], meanKwh: 105, totalKwh: 2625, hours: repeatedHours },
      ],
    } });
  });
}

test("daily profiles retain UTC filter state and show group, scale, exports and raw DST offsets", async ({ page }) => {
  await mockProfiles(page);
  const firstRequest = page.waitForRequest((request) => request.url().includes("/api/explore/demand-profiles?") && request.url().includes("end=2025-10-28"));
  await page.goto("/explore?view=profiles&area=NO2&start=2025-10-24&end=2025-10-27");
  await firstRequest;
  await expect(page.getByRole("heading", { name: "Daily demand profiles" })).toBeVisible();
  await page.getByRole("button", { name: "About Daily profile bands" }).click();
  await expect(page.getByRole("dialog", { name: "Daily profile bands" })).toContainText("not a confidence interval");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("combobox", { name: "Price area", exact: true })).toHaveAttribute("data-value", "NO2");
  await expect(page.getByText("Synthetic fixture example")).toBeVisible();
  await expect(page.getByRole("img", { name: /NO2 weekday and weekend daily household demand profiles in kWh/ })).toBeVisible();
  await expect(page.getByLabel("Displayed profile groups")).toContainText("1 days");
  await page.getByRole("combobox", { name: "Profile groups" }).click();
  await page.getByRole("option", { name: "Seasons" }).click();
  await expect(page.getByRole("img", { name: /NO2 seasonal daily household demand profiles/ })).toBeVisible();
  await page.getByRole("combobox", { name: "Profile scale" }).click();
  await page.getByRole("option", { name: "Shape · % of daily mean" }).click();
  await expect(page.getByRole("img", { name: /percent of daily mean/ })).toBeVisible();
  await page.getByText("Hourly profile values", { exact: true }).click();
  await expect(page.getByRole("region", { name: "Hourly profile values" }).getByRole("row")).toHaveCount(25);
  await page.getByRole("button", { name: "Coverage & method" }).click();
  await expect(page.getByRole("dialog", { name: "Coverage & method" })).toContainText("not a confidence interval");
  await expect(page.getByRole("dialog", { name: "Coverage & method" })).toContainText("These exclusion categories may overlap");
  await page.getByRole("button", { name: "Close Coverage & method" }).click();
  await page.getByText("Observed day detail", { exact: true }).click();
  await page.getByRole("combobox", { name: "Observed Oslo date" }).click();
  await page.getByRole("option", { name: "2025-10-26" }).click();
  const raw = page.getByRole("region", { name: "Raw hourly observations for 2025-10-26" });
  await expect(raw).toContainText("02:00 UTC+02:00");
  await expect(raw).toContainText("02:00 UTC+01:00");
  await expect(page.getByText("25-hour daylight-saving day", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Export" }).click();
  await expect(page.getByRole("button", { name: "Profile values CSV" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Observed days CSV" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Data & method JSON" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /^Date range:/ }).click();
  await page.getByRole("dialog", { name: "Choose date range" }).getByLabel("End date", { exact: true }).fill("2025-10-28");
  await page.getByRole("button", { name: "Use dates" }).click();
  const nextRequest = page.waitForRequest((request) => request.url().includes("/api/explore/demand-profiles?") && request.url().includes("end=2025-10-29"));
  await page.getByRole("button", { name: "Apply view" }).click();
  await nextRequest;
  await expect(page).toHaveURL(/end=2025-10-28/);
  await page.goBack();
  await expect(page).toHaveURL(/end=2025-10-27/);
});

test("profile empty state offers a date range and keeps method and raw export available", async ({ page }) => {
  await mockProfiles(page, true);
  await page.goto("/explore?view=profiles&area=NO1&start=2025-10-24&end=2025-10-27");
  await expect(page.getByText("No complete 24-hour Oslo days match this range.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Coverage & method" })).toBeVisible();
  await page.getByRole("button", { name: "Export" }).click();
  await expect(page.getByRole("button", { name: "Observed days CSV" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Data & method JSON" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByText("Observed day detail", { exact: true }).click();
  await expect(page.getByText("No observed days in this date range.", { exact: false })).toBeVisible();
});

test("fixture API delivers the profile contract without a browser mock", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/explore?view=profiles&area=NO1&start=2025-01-01&end=2025-01-07");
  await expect(page.getByRole("heading", { name: "Daily demand profiles" })).toBeVisible();
  await expect(page.getByText("Synthetic fixture example")).toBeVisible();
  await page.getByRole("button", { name: "Export", exact: true }).click();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: /^Download .* as PNG$/ }).click();
  await (await downloaded).saveAs(testInfo.outputPath("daily-profiles.png"));
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Coverage & method" })).toBeVisible();
  await page.getByRole("button", { name: "Coverage & method" }).click();
  await expect(page.getByRole("dialog", { name: "Coverage & method" })).toContainText("UTC midnight");
  await page.getByRole("button", { name: "Close Coverage & method" }).click();
  await page.getByText("Representative observed days", { exact: true }).click();
  const representative = page.getByRole("button", { name: /Inspect .* representative day/ }).first();
  await expect(representative).toBeVisible();
  await representative.focus();
  await page.keyboard.press("Enter");
  const detail = page.locator("details.profile-days");
  await expect(detail).toHaveAttribute("open", "");
  await expect(detail.locator("summary")).toBeFocused();
  await expect(detail.getByRole("region", { name: /Raw hourly observations for/ })).toBeVisible();
  for (const theme of ["Light", "Dark"]) {
    await page.getByRole("button", { name: theme, exact: true }).click();
    await expect(page.getByRole("heading", { name: "Daily demand profiles" })).toBeVisible();
    const pageWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(pageWidth).toBeLessThanOrEqual(325);
  }
});

test("profile request shows loading and can retry a failed response", async ({ page }) => {
  await mockProfiles(page);
  let requests = 0;
  await page.route("**/api/explore/demand-profiles?**", async (route) => {
    requests += 1;
    if (requests === 1) {
      await new Promise((resolve) => setTimeout(resolve, 150));
      await route.fulfill({ status: 503, json: { detail: "Temporary profile outage" } });
    } else await route.fallback();
  });
  await page.goto("/explore?view=profiles&area=NO1&start=2025-10-24&end=2025-10-27");
  await expect(page.getByText("Loading published observations…")).toBeVisible();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "Daily demand profiles" })).toBeVisible();
  expect(requests).toBe(2);
});

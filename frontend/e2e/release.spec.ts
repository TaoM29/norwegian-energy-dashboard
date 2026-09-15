import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("overview filters survive reload and export values", async ({ page, request }, testInfo) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Supply & demand" }),
  ).toBeVisible();
  await expect(
    page.getByRole("note").filter({ hasText: "Synthetic fixture data" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "NO2", exact: true }).click();
  await expect(page).toHaveURL(/area=NO2/);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "NO2", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export daily data" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.csv$/);
  const csv = await readFile((await file.path())!, "utf8");
  const [header, ...rows] = csv.trim().split("\n");
  expect(header).toBe("date_utc,production_mwh,consumption_mwh,production_partial,consumption_partial");
  const query = new URL(page.url()).searchParams;
  // The overview API uses an exclusive end while the browser date is inclusive.
  const end = new Date(`${query.get("end")}T00:00:00Z`);
  end.setUTCDate(end.getUTCDate() + 1);
  const result = await request.get(`/api/overview?area=NO2&start=${query.get("start")}&end=${end.toISOString().slice(0, 10)}`);
  const overview = await result.json();
  expect(rows).toHaveLength(overview.daily.length);
  const first = rows[0].split(",");
  expect(first[0]).toBe(overview.daily[0].date);
  expect(Number(first[1])).toBe(overview.daily[0].production.mwh);
  expect(Number(first[2])).toBe(overview.daily[0].consumption.mwh);
  await expect(page.locator("#main")).toHaveAttribute("data-painted-query", /^NO2\//);
  await page.screenshot({ path: testInfo.outputPath("overview-desktop.png"), fullPage: true, animations: "disabled" });
});

test("analysis and regional workspaces use the offline snapshots", async ({
  page,
}) => {
  await page.goto("/explore?area=NO1&start=2025-11-01&end=2025-11-28");
  await expect(
    page.getByRole("heading", { name: "Group totals" }),
  ).toBeVisible();
  await page.goto("/diagnostics?area=NO1&start=2025-11-01&end=2025-11-28");
  await expect(
    page.getByRole("heading", { name: "Centered rolling correlation" }),
  ).toBeVisible();
  await page.goto("/regional");
  await expect(
    page.getByRole("heading", { name: "Regional values" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Seasonal transport", exact: true }),
  ).toBeVisible({ timeout: 30000 });
});

test("prepared forecasts are readable with public custom jobs disabled", async ({
  page,
  request,
}, testInfo) => {
  const response = await request.post("/api/forecasts/jobs", {
    data: { kind: "sarimax" },
  });
  expect(response.status()).toBe(403);
  await page.goto("/");
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "Forecasts" })
    .click();
  await expect(page.getByLabel("Start target date (UTC)", { exact: true })).toHaveValue("2025-11-01");
  await expect(
    page.getByRole("heading", { name: "Accuracy and interval quality" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Run SARIMAX job" }),
  ).toHaveCount(0);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download metadata JSON" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.json$/);
  const exported = JSON.parse(await readFile((await file.path())!, "utf8"));
  expect(exported.metadata.synthetic).toBe(true);
  expect(exported.config.horizon_hours).toBe(24);
  expect(exported.coverage.matchedOrigins).toBe(10);
  expect(exported.calibration.NO1.seasonal_naive.observations).toBeGreaterThan(0);
  expect(exported.origins.selectionFrozenBeforeHoldout).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("forecast-desktop.png"), animations: "disabled" });
});

test("methods and navigation fit mobile and support keyboard focus", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/methods");
  await expect(
    page.getByRole("heading", { name: "Published data coverage" }),
  ).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to analysis" }),
  ).toBeFocused();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await expect(
    page.getByRole("link", { name: "the original IND320 project" }),
  ).toBeVisible();
  await expect(page.getByText(/2025-01-01 to 2026-01-01/)).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("methods-mobile.png"), animations: "disabled" });
});

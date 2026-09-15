import { test, expect } from "@playwright/test";

test("overview filters survive reload and export values", async ({ page }) => {
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
  expect((await download).suggestedFilename()).toMatch(/\.csv$/);
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
}) => {
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
  expect((await download).suggestedFilename()).toMatch(/\.json$/);
});

test("methods and navigation fit mobile and support keyboard focus", async ({
  page,
}) => {
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
});

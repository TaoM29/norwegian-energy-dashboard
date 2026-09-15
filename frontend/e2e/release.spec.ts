import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("overview filters survive reload and export values", async ({
  page,
  request,
}, testInfo) => {
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
  await page.getByRole("button", { name: "Export", exact: true }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export daily data" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.csv$/);
  const csv = await readFile((await file.path())!, "utf8");
  const [header, ...rows] = csv.trim().split("\n");
  expect(header).toBe(
    "date_utc,production_mwh,consumption_mwh,production_partial,consumption_partial",
  );
  const query = new URL(page.url()).searchParams;
  // The overview API uses an exclusive end while the browser date is inclusive.
  const end = new Date(`${query.get("end")}T00:00:00Z`);
  end.setUTCDate(end.getUTCDate() + 1);
  const result = await request.get(
    `/api/overview?area=NO2&start=${query.get("start")}&end=${end.toISOString().slice(0, 10)}`,
  );
  const overview = await result.json();
  expect(rows).toHaveLength(overview.daily.length);
  const first = rows[0].split(",");
  expect(first[0]).toBe(overview.daily[0].date);
  expect(Number(first[1])).toBe(overview.daily[0].production.mwh);
  expect(Number(first[2])).toBe(overview.daily[0].consumption.mwh);
  await expect(page.locator("#main")).toHaveAttribute(
    "data-painted-query",
    /^NO2\//,
  );
  await page.screenshot({
    path: testInfo.outputPath("overview-desktop.png"),
    fullPage: true,
    animations: "disabled",
  });
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
  ).toBeHidden();
  await page.getByRole("tab", { name: "Snow model", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Seasonal transport", exact: true }),
  ).toBeVisible({ timeout: 30000 });
});

test("prepared forecasts are readable with public custom jobs disabled", async ({
  page,
  request,
}, testInfo) => {
  const renderErrors: string[] = [];
  page.on("console", (message) => {
    if (/Cannot update a component|setState.*render/.test(message.text()))
      renderErrors.push(message.text());
  });
  const response = await request.post("/api/forecasts/jobs", {
    data: { kind: "sarimax" },
  });
  expect(response.status()).toBe(403);
  await page.goto("/");
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "Forecasts" })
    .click();
  await expect(
    page.getByRole("button", { name: /^Target dates:/ }),
  ).toContainText("1 Nov 2025");
  await page.getByText("Metric details and downloads", { exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Accuracy and interval quality" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Run SARIMAX job" }),
  ).toHaveCount(0);
  const area = page
    .getByRole("form", { name: "Stored result filters" })
    .getByRole("combobox", { name: "Area", exact: true });
  await area.selectOption("NO2");
  await expect(page).toHaveURL(/area=NO2/);
  await area.selectOption("NO3");
  await expect(page).toHaveURL(/area=NO3/);
  await page.goBack();
  await expect(
    page.getByRole("heading", { name: "Energy overview", exact: true }),
  ).toBeVisible();
  await page.goForward();
  await expect(area).toHaveValue("NO3");
  await page.reload();
  await expect(area).toHaveValue("NO3");
  expect(renderErrors).toEqual([]);
  await page
    .getByRole("button", { name: "Export", exact: true })
    .first()
    .click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download metadata JSON" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.json$/);
  const exported = JSON.parse(await readFile((await file.path())!, "utf8"));
  expect(exported.metadata.synthetic).toBe(true);
  expect(exported.config.horizon_hours).toBe(24);
  expect(exported.coverage.matchedOrigins).toBe(10);
  expect(exported.calibration.NO1.seasonal_naive.observations).toBeGreaterThan(
    0,
  );
  expect(exported.origins.selectionFrozenBeforeHoldout).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("forecast-desktop.png"),
    animations: "disabled",
  });
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
  await page.screenshot({
    path: testInfo.outputPath("methods-mobile.png"),
    animations: "disabled",
  });
});

test("theme follows the system and preserves an explicit choice across pages", async ({
  page,
}, testInfo) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/?area=NO2&start=2025-11-01&end=2025-11-28");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(
    page.getByRole("heading", { name: "Supply & demand" }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("overview-dark.png"),
    fullPage: true,
    animations: "disabled",
  });
  const darkSurface = await page
    .locator(".site-header")
    .evaluate((node) => getComputedStyle(node).backgroundColor);
  await page.getByRole("button", { name: "Light", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  expect(
    await page
      .locator(".site-header")
      .evaluate((node) => getComputedStyle(node).backgroundColor),
  ).not.toBe(darkSurface);
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "Explore", exact: true })
    .click();
  await expect(page).toHaveURL(/area=NO2/);
  await expect(
    page.getByRole("heading", { name: "Group totals" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Light", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Dark", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({
    path: testInfo.outputPath("explore-dark.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "System", exact: true }).click();
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("mobile pages keep navigation, guidance and theme controls usable", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByRole("button", { name: "Dark", exact: true }).click();
  await page.getByText("New here? A 30-second guide", { exact: true }).click();
  await expect(page.getByText(/one million kWh/)).toBeVisible();
  for (const path of [
    "/",
    "/explore",
    "/forecasts",
    "/diagnostics",
    "/regional",
    "/methods",
  ]) {
    await page.goto(path);
    const menu = page.getByRole("button", { name: "Menu", exact: true });
    const navigation = page.getByRole("navigation", {
      name: "Main navigation",
    });
    await expect(navigation).toBeHidden();
    await menu.click();
    await expect(navigation).toBeVisible();
    await expect(menu).toHaveAttribute("aria-expanded", "true");
    await navigation
      .getByRole("link", { name: "Explore", exact: true })
      .focus();
    await page.keyboard.press("Escape");
    await expect(navigation).toBeHidden();
    await expect(menu).toBeFocused();
    await expect(
      page.getByRole("button", { name: "Dark", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(390);
  }
  await page.screenshot({
    path: testInfo.outputPath("methods-mobile-dark.png"),
    animations: "disabled",
  });
  await page.goto("/diagnostics?area=NO1&start=2025-11-01&end=2025-11-28");
  await expect(page.getByLabel("Window, hours", { exact: true })).toBeHidden();
  await page.locator(".method-settings summary").click();
  await expect(page.getByLabel("Window, hours", { exact: true })).toBeVisible();
  await page
    .getByRole("tab", { name: "Weather & energy", exact: true })
    .press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Seasonal patterns", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
});

test("regional table sorts and opens details without changing the selected view", async ({
  page,
}, testInfo) => {
  await page.goto("/?area=NO1&start=2025-11-01&end=2025-11-28");
  await page.getByRole("button", { name: "Dark", exact: true }).click();
  await page.getByLabel("Sort regions").selectOption("region");
  await expect(
    page.locator(".region-comparison tbody tr").first(),
  ).toContainText("NO1");
  const trigger = page.getByRole("button", {
    name: "Inspect Northern Norway",
    exact: true,
  });
  await trigger.click();
  const drawer = page.getByRole("dialog", {
    name: "Northern Norway",
    exact: true,
  });
  await expect(
    drawer.getByRole("heading", { name: "Generation mix" }),
  ).toBeVisible();
  await expect(page).toHaveURL(/area=NO1/);
  await page.screenshot({
    path: testInfo.outputPath("region-drawer-dark.png"),
    animations: "disabled",
  });
  await page.keyboard.press("Escape");
  await expect(drawer).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await trigger.press("Enter");
  await drawer.getByRole("button", { name: "View this region" }).click();
  await expect(page).toHaveURL(/area=NO4/);
  await expect(
    page.getByRole("button", { name: "NO4", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});

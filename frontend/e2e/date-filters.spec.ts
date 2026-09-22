import { test, expect } from "@playwright/test";

// A non-UTC browser catches date-only values accidentally converted through local time.
test.use({ timezoneId: "America/Los_Angeles" });

test("range picker stages, validates, cancels and applies inclusive UTC dates", async ({
  page,
}, testInfo) => {
  await page.goto("/?area=NO1&start=2025-03-01&end=2025-03-28");
  const trigger = page.getByRole("button", { name: /^Date range:/ });
  await trigger.click();
  const calendar = page.getByRole("dialog", { name: "Choose date range" });
  await expect(calendar.locator(".rdp-month")).toHaveCount(2);
  await calendar
    .getByRole("combobox", { name: "Month, calendar 1", exact: true })
    .click();
  await page.getByRole("option", { name: "May", exact: true }).click();
  await expect(
    calendar.getByRole("combobox", { name: "Month, calendar 1", exact: true }),
  ).toHaveText("May");
  await expect(
    calendar.getByRole("combobox", { name: "Month, calendar 2", exact: true }),
  ).toHaveText("June");
  await calendar
    .getByRole("combobox", { name: "Month, calendar 2", exact: true })
    .click();
  await page.getByRole("option", { name: "August", exact: true }).click();
  await expect(
    calendar.getByRole("combobox", { name: "Month, calendar 1", exact: true }),
  ).toHaveText("July");
  await expect(page).toHaveURL(/start=2025-03-01&end=2025-03-28/);

  await calendar.getByLabel("Start date", { exact: true }).fill("2025-02-30");
  await expect(
    calendar.getByRole("button", { name: "Apply dates" }),
  ).toBeDisabled();
  await calendar.getByLabel("Start date", { exact: true }).fill("2025-03-29");
  await expect(calendar).toContainText("End date must be on or after");
  await calendar.getByLabel("End date", { exact: true }).fill("2025-03-30");
  await calendar.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page).toHaveURL(/end=2025-03-28/);
  await expect(trigger).toBeFocused();
  await trigger.press("Enter");
  await expect(calendar.getByLabel("Start date", { exact: true })).toHaveValue(
    "2025-03-01",
  );
  await calendar.getByLabel("Start date", { exact: true }).fill("2025-03-29");
  await calendar.getByLabel("End date", { exact: true }).fill("2025-03-30");
  const api = page.waitForRequest(
    (request) =>
      request.url().includes("/api/overview?") &&
      request.url().includes("end=2025-03-31"),
  );
  await calendar.getByRole("button", { name: "Apply dates" }).click();
  await api;
  await expect(page).toHaveURL(/start=2025-03-29&end=2025-03-30/);
  await expect(trigger).toContainText("29 Mar 2025 – 30 Mar 2025");
  await trigger.click();
  await calendar
    .getByRole("button", { name: "Latest 7 days", exact: true })
    .click();
  await expect(calendar.getByLabel("End date", { exact: true })).toHaveValue(
    "2025-12-31",
  );
  await expect(calendar.getByLabel("Start date", { exact: true })).toHaveValue(
    "2025-12-25",
  );
  await page.screenshot({
    path: testInfo.outputPath("date-range-desktop.png"),
    animations: "disabled",
  });
  await page.keyboard.press("Escape");
  await expect(calendar).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("applied filters, navigation hrefs and Back preserve the observation workspace", async ({
  page,
}) => {
  await page.goto("/explore?area=NO2&start=2025-11-01&end=2025-11-28");
  await page.getByText("Group totals and coverage", { exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Group totals" }),
  ).toBeVisible();
  const trigger = page.getByRole("button", { name: /^Date range:/ });
  await trigger.click();
  const calendar = page.getByRole("dialog", { name: "Choose date range" });
  await calendar.getByLabel("End date", { exact: true }).fill("2025-11-20");
  await calendar.getByRole("button", { name: "Use dates" }).click();
  await expect(
    page.getByText("Changes not applied", { exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL(/end=2025-11-28/);
  await page.getByRole("button", { name: "Discard changes" }).click();
  await expect(trigger).toContainText("28 Nov 2025");
  await trigger.click();
  await calendar.getByLabel("End date", { exact: true }).fill("2025-11-20");
  await calendar.getByRole("button", { name: "Use dates" }).click();
  await page.getByRole("button", { name: "Apply view", exact: true }).click();
  await expect(page).toHaveURL(/end=2025-11-20/);
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  await expect(
    nav.getByRole("link", { name: "Regional", exact: true }),
  ).toHaveAttribute(
    "href",
    "/regional?area=NO2&start=2025-11-01&end=2025-11-20",
  );
  await page.goBack();
  await expect(trigger).toContainText("28 Nov 2025");
  await page.goForward();
  await expect(trigger).toContainText("20 Nov 2025");
  await nav.getByRole("link", { name: "Forecasts", exact: true }).click();
  await page.getByText("Metric details and downloads", { exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Accuracy and interval quality" }),
  ).toBeVisible();
  await page
    .getByRole("form", { name: "Stored result filters" })
    .getByRole("combobox", { name: "Forecast price area", exact: true })
    .click();
  await page.getByRole("option", { name: "NO3", exact: true }).click();
  await expect(
    nav.getByRole("link", { name: "Explore", exact: true }),
  ).toHaveAttribute(
    "href",
    "/explore?area=NO2&start=2025-11-01&end=2025-11-20",
  );
  await page.reload();
  await nav.getByRole("link", { name: "Methods", exact: true }).click();
  await nav.getByRole("link", { name: "Explore", exact: true }).click();
  await expect(page).toHaveURL(/area=NO2&start=2025-11-01&end=2025-11-20/);
});

test("diagnostic drafts retain applied results and regional groups need no modifier keys", async ({
  page,
}) => {
  await page.goto("/diagnostics?area=NO1&start=2025-11-01&end=2025-11-28");
  await expect(
    page.getByRole("heading", { name: "Centered rolling correlation" }),
  ).toBeVisible();
  await page.getByRole("combobox", { name: "Analysis" }).click();
  await page.getByRole("option", { name: "Seasonal patterns", exact: true }).click();
  await expect(
    page.getByText("Changes not applied", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Centered rolling correlation" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Discard changes" }).click();
  await expect(page.getByRole("combobox", { name: "Analysis" })).toHaveAttribute("data-value", "correlation");
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Regional", exact: true })
    .click();
  await page.getByText("Regional values and coverage", { exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Regional values" }),
  ).toBeVisible();
  const groups = page.getByRole("group", {
    name: "Energy groups",
    exact: true,
  });
  await page.getByText(/Energy groups · \d+ selected/).click();
  await groups.getByRole("checkbox", { name: "hydro", exact: true }).check();
  await expect(
    groups.getByRole("checkbox", { name: "solar", exact: true }),
  ).toBeChecked();
  await expect(
    page.getByText("Changes not applied", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Compare energy" }).click();
  await expect(page).toHaveURL(/groups=hydro%2Csolar/);
  await expect(page.getByText(/Applied: production · hydro, solar/)).toBeVisible();
});

test("mobile calendar fits, highlights a selected range, and preserves dates across reload", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?area=NO1&start=2025-11-01&end=2025-11-28");
  await page.getByRole("button", { name: "Dark", exact: true }).click();
  await page.getByRole("button", { name: /^Date range:/ }).click();
  const calendar = page.getByRole("dialog", { name: "Choose date range" });
  await expect(calendar.locator(".rdp-month")).toHaveCount(1);
  await calendar.getByLabel("Start date", { exact: true }).fill("");
  await calendar.getByLabel("End date", { exact: true }).fill("");
  await calendar
    .getByRole("button", { name: /Monday, November 3rd, 2025/ })
    .click();
  await calendar
    .getByRole("button", { name: /Friday, November 7th, 2025/ })
    .click();
  await expect(calendar.getByLabel("Start date", { exact: true })).toHaveValue(
    "2025-11-03",
  );
  await expect(calendar.getByLabel("End date", { exact: true })).toHaveValue(
    "2025-11-07",
  );
  const box = await calendar.boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(390);
  expect(box!.y + box!.height).toBeLessThanOrEqual(844);
  await page.screenshot({
    path: testInfo.outputPath("date-range-mobile-dark.png"),
    animations: "disabled",
  });
  await calendar.getByRole("button", { name: "Apply dates" }).click();
  await page.reload();
  await expect(
    page.getByRole("button", { name: /^Date range:/ }),
  ).toContainText("3 Nov 2025 – 7 Nov 2025");
});

test("forecast target dates select a matching saved origin and preserve it on reload", async ({
  page,
}) => {
  await page.goto("/forecasts?area=NO3");
  const filters = page.getByRole("form", { name: "Stored result filters" });
  await filters.getByText(/Model & evaluation options · \d+ models/).click();
  const origin = filters.getByRole("combobox", {
    name: "Matched forecast origin",
  });
  await expect(origin).toHaveAttribute("data-value", /2025-12-01/);
  await expect(
    page
      .getByRole("navigation")
      .getByRole("link", { name: "Explore", exact: true }),
  ).toHaveAttribute("href", "/explore?area=NO3");
  await filters.getByRole("button", { name: /^Target dates:/ }).click();
  const calendar = page.getByRole("dialog", { name: "Choose target dates" });
  await calendar.getByLabel("Start date", { exact: true }).fill("2025-11-01");
  await calendar.getByLabel("End date", { exact: true }).fill("2025-11-01");
  await calendar.getByRole("button", { name: "Apply dates" }).click();
  await expect(origin).toHaveAttribute("data-value", /2025-11-01/);
  await expect(page).toHaveURL(/origin=2025-11-01/);
  await page.reload();
  await filters.getByText(/Model & evaluation options · \d+ models/).click();
  await expect(origin).toHaveAttribute("data-value", /2025-11-01/);
  await expect(
    filters.getByRole("button", { name: /^Target dates:/ }),
  ).toContainText("1 Nov 2025");
});

test("chart exports stay together and preserve downloadable values", async ({
  page,
}) => {
  await page.goto("/explore?area=NO1&start=2025-11-01&end=2025-11-28");
  const panel = page.locator("section").filter({
    has: page.getByRole("heading", {
      name: "Production through time",
      exact: true,
    }),
  });
  await expect(panel.getByRole("button", { name: "Data CSV" })).toBeHidden();
  await panel.getByRole("button", { name: "Export", exact: true }).click();
  const options = page.getByRole("dialog", { name: "Export options" });
  await expect(options.getByRole("button", { name: /as PNG/ })).toBeVisible();
  const download = page.waitForEvent("download");
  await options.getByRole("button", { name: "Data CSV" }).click();
  expect((await download).suggestedFilename()).toMatch(
    /NO1-production.*\.csv$/,
  );
  await page.keyboard.press("Escape");
  await expect(
    panel.getByRole("button", { name: "Export", exact: true }),
  ).toBeFocused();
});

test("overview compares equal UTC windows and preserves history", async ({
  page,
  request,
}) => {
  await page.goto("/?area=NO1&start=2025-02-01&end=2025-02-28");
  const comparison = page.getByRole("region", {
    name: "Previous period comparison",
  });
  await expect(comparison).toContainText("2025-01-04–2025-01-31");
  const current = await (
    await request.get("/api/overview?area=NO1&start=2025-02-01&end=2025-03-01")
  ).json();
  const previous = await (
    await request.get("/api/overview?area=NO1&start=2025-01-04&end=2025-02-01")
  ).json();
  const change =
    ((current.headline.production.mwh - previous.headline.production.mwh) /
      previous.headline.production.mwh) *
    100;
  await expect(comparison).toContainText(
    `${change < 0 ? "−" : change > 0 ? "+" : ""}${new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 }).format(Math.abs(change))} %`,
  );
  await comparison
    .getByRole("button", { name: "View previous period" })
    .click();
  await expect(page).toHaveURL(/start=2025-01-04&end=2025-01-31/);
  await page.goBack();
  await expect(page).toHaveURL(/start=2025-02-01&end=2025-02-28/);
  await page.goto("/?area=NO1&start=2025-01-01&end=2025-01-28");
  await expect(comparison).toContainText("Choose a later or shorter period");
});

test("forecast settings drawer keeps training dates usable and preserves API boundaries", async ({
  page,
}) => {
  await page.route("**/api/forecasts/capabilities", (route) =>
    route.fulfill({ json: { customJobsEnabled: true } }),
  );
  let submitted:
    { config: { start: string; end: string; horizon: number } } | undefined;
  await page.route("**/api/forecasts/jobs", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    submitted = route.request().postDataJSON();
    await route.fulfill({
      status: 400,
      json: { detail: "Test intercepted submission" },
    });
  });
  await page.goto("/forecasts");
  const trigger = page.getByRole("button", {
    name: "Experiment settings",
    exact: true,
  });
  await expect(
    page.getByRole("dialog", { name: "Experiment settings", exact: true }),
  ).toBeHidden();
  await trigger.click();
  const drawer = page.getByRole("dialog", {
    name: "Experiment settings",
    exact: true,
  });
  await drawer.getByRole("combobox", { name: "Experiment type" }).click();
  await page
    .getByRole("option", { name: "Custom SARIMAX", exact: true })
    .click();
  await expect(
    drawer.getByRole("button", { name: "Run evaluation job" }),
  ).toHaveCount(0);
  await drawer.getByRole("button", { name: /^Training dates:/ }).click();
  const calendar = page.getByRole("dialog", { name: "Choose training dates" });
  await calendar.getByLabel("Start date", { exact: true }).fill("2025-03-29");
  await calendar.getByLabel("End date", { exact: true }).fill("2025-03-30");
  await calendar.getByRole("button", { name: "Use dates" }).click();
  await drawer.getByRole("button", { name: /^Training dates:/ }).click();
  await page.keyboard.press("Escape");
  await expect(calendar).toBeHidden();
  await expect(drawer).toBeVisible();
  const setup = drawer.getByRole("region", {
    name: "Training period to forecast horizon",
  });
  await expect(
    setup
      .getByRole("listitem")
      .filter({ hasText: "2 · Forecast issue / start" }),
  ).toContainText("2 Apr 2025, 00:00 UTC");
  await expect(
    setup.getByRole("listitem").filter({ hasText: "3 · Ahead horizon" }),
  ).toContainText("3 Apr 2025, 00:00 UTC");
  await setup.getByRole("button", { name: "72 hours", exact: true }).click();
  await expect(
    setup.getByRole("listitem").filter({ hasText: "3 · Ahead horizon" }),
  ).toContainText("5 Apr 2025, 00:00 UTC");
  await drawer.getByRole("button", { name: "Run SARIMAX job" }).click();
  await expect.poll(() => submitted?.config.end).toBe("2025-03-31");
  expect(submitted?.config.start).toBe("2025-03-29");
  expect(submitted?.config.horizon).toBe(72);
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("regional tasks load independently and preserve mode history", async ({
  page,
}) => {
  const calls: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/regional/")) calls.push(request.url());
  });
  await page.goto(
    "/regional?mode=energy&area=NO1&start=2025-11-01&end=2025-11-28",
  );
  await page.getByText("Regional values and coverage", { exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Regional values", exact: true }),
  ).toBeVisible();
  expect(calls.some((url) => url.includes("snow-drift"))).toBe(false);
  await expect(
    page.getByRole("button", { name: "Run snow model" }),
  ).toHaveCount(0);
  await page.getByRole("tab", { name: "Snow model", exact: true }).click();
  await expect(page).toHaveURL(/mode=snow/);
  await expect(
    page.getByRole("heading", { name: "Seasonal transport", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /^Date range:/ })).toHaveCount(
    0,
  );
  calls.length = 0;
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Seasonal transport", exact: true }),
  ).toBeVisible();
  expect(calls.some((url) => url.includes("summary"))).toBe(false);
  await page.goBack();
  await expect(
    page.getByRole("tab", { name: "Energy comparison", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await page.getByText("Regional values and coverage", { exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Regional values", exact: true }),
  ).toBeVisible();
});

test("period comparison withholds changes for incomplete observations", async ({
  page,
}) => {
  await page.route("**/api/overview?**", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    if (body.query.start === "2025-01-04")
      body.headline.consumption.partial = true;
    await route.fulfill({ response, json: body });
  });
  await page.goto("/?area=NO1&start=2025-02-01&end=2025-02-28");
  const comparison = page.getByRole("region", {
    name: "Previous period comparison",
  });
  const consumption = comparison.getByRole("article").filter({
    has: page.getByRole("heading", { name: "Energy consumed", exact: true }),
  });
  await expect(consumption).toContainText("Change unavailable");
  await expect(consumption).not.toContainText("% from the previous period");
  await expect(comparison).toContainText(
    "Changes are withheld wherever either period is incomplete",
  );
});

test("styled selectors support keyboard choice and help works by hover, focus and click", async ({
  page,
}) => {
  await page.goto("/explore?area=NO1&start=2025-11-01&end=2025-11-28");
  const area = page.getByRole("combobox", { name: "Price area", exact: true });
  await area.focus();
  await area.press("ArrowDown");
  const northern = page.getByRole("option", {
    name: "NO4 · Northern Norway",
    exact: true,
  });
  await expect(northern).toBeVisible();
  await expect(
    page.getByRole("option", { name: "NO1 · Eastern Norway", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("End");
  await expect(
    page.getByRole("option", { name: "NO5 · Western Norway", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(area).toHaveAttribute("data-value", "NO5");
  await expect(area).toBeFocused();
  await page.getByText("Group totals and coverage", { exact: true }).click();
  const totals = page.getByRole("button", {
    name: "About How totals are calculated",
    exact: true,
  });
  await totals.hover();
  await expect(
    page.getByRole("dialog", { name: "How totals are calculated", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await totals.focus();
  await expect(
    page.getByRole("dialog", { name: "How totals are calculated", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  const sources = page.getByRole("button", {
    name: "About this view",
    exact: true,
  });
  await sources.click();
  const panel = page.getByRole("dialog", {
    name: "About this view",
    exact: true,
  });
  await expect(panel).toContainText("A gap means missing observations");
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(sources).toBeFocused();
});

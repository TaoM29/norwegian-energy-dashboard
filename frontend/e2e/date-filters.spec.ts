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
  await expect(
    page.getByRole("heading", { name: "Accuracy and interval quality" }),
  ).toBeVisible();
  await page
    .getByRole("form", { name: "Stored result filters" })
    .getByRole("combobox", { name: "Area", exact: true })
    .selectOption("NO3");
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
  await page
    .getByRole("tab", { name: "Seasonal patterns", exact: true })
    .click();
  await expect(
    page.getByText("Changes not applied", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Centered rolling correlation" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Discard changes" }).click();
  await expect(
    page.getByRole("tab", { name: "Weather & energy", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Regional", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Regional values" }),
  ).toBeVisible();
  const groups = page.getByRole("group", { name: "Groups", exact: true });
  await groups.getByRole("checkbox", { name: "hydro", exact: true }).check();
  await expect(
    groups.getByRole("checkbox", { name: "solar", exact: true }),
  ).toBeChecked();
  await expect(
    page.getByText("Changes not applied", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Apply analysis" }).click();
  await expect(page).toHaveURL(/groups=hydro%2Csolar/);
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
  const origin = filters.getByRole("combobox", {
    name: "Matched forecast origin",
  });
  await expect(origin).toHaveValue(/2025-12-01/);
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
  await expect(origin).toHaveValue(/2025-11-01/);
  await expect(page).toHaveURL(/origin=2025-11-01/);
  await page.reload();
  await expect(origin).toHaveValue(/2025-11-01/);
  await expect(
    filters.getByRole("button", { name: /^Target dates:/ }),
  ).toContainText("1 Nov 2025");
});

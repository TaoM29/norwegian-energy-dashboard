import { expect, test } from "@playwright/test";

const studies = [
  {
    name: "temperature sensitivity",
    view: "sensitivity",
    path: "/api/diagnostics/sensitivity",
    exportName: "Export study",
    missingMessage: "No saved demand sensitivity study is available yet.",
  },
  {
    name: "unusual demand",
    view: "demand_anomalies",
    path: "/api/diagnostics/demand-anomalies",
    exportName: "Export anomaly study",
    missingMessage: "No saved demand-anomaly study is available yet.",
  },
  {
    name: "persistent demand changes",
    view: "demand_changes",
    path: "/api/diagnostics/demand-changes",
    exportName: "Export demand-change study",
    missingMessage: "No saved demand-change study is available yet.",
  },
] as const;

for (const study of studies) {
  test(`${study.name}: an unpublished artifact points to available data`, async ({ page }) => {
    await page.route("**/api/diagnostics/**", (route) => {
      if (new URL(route.request().url()).pathname !== study.path) return route.continue();
      return route.fulfill({ status: 404, json: { detail: study.missingMessage } });
    });
    await page.goto(`/diagnostics?view=${study.view}`);

    const missing = page.getByRole("status").filter({ hasText: "This study hasn’t been published yet" });
    await expect(missing).toBeVisible();
    await expect(missing.getByRole("link", { name: /Explore available data/ })).toHaveAttribute("href", "/explore");
    await expect(missing.getByRole("button", { name: "Retry" })).toHaveCount(0);
    await expect(page.getByRole("alert").filter({ hasText: "Couldn’t load this study" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: study.exportName })).toHaveCount(0);
  });

  test(`${study.name}: a temporary failure can retry without stale findings`, async ({ page }) => {
    let calls = 0;
    let unavailable = true;
    await page.route("**/api/diagnostics/**", (route) => {
      if (new URL(route.request().url()).pathname !== study.path) return route.continue();
      calls += 1;
      return unavailable
        ? route.fulfill({ status: 503, json: { detail: "Temporary study outage" } })
        : route.continue();
    });
    await page.goto(`/diagnostics?view=${study.view}`);

    const failure = page.getByRole("alert").filter({ hasText: "Couldn’t load this study" });
    await expect(failure).toContainText("Temporary study outage");
    await expect(page.getByRole("button", { name: study.exportName })).toHaveCount(0);
    unavailable = false;
    await failure.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByRole("button", { name: study.exportName })).toBeVisible();
    await expect(failure).toHaveCount(0);
    expect(calls).toBeGreaterThanOrEqual(2);
  });
}

import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
const root = path.resolve(__dirname, "..");
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: "http://127.0.0.1:3100", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `${process.env.PYTHON || "python"} -m uvicorn backend.main:app --host 127.0.0.1 --port 8100`,
      cwd: root,
      url: "http://127.0.0.1:8100/api/ready",
      env: {
        ENERGY_DATABASE: path.join(root, "data/fixture/energy.sqlite"),
        WEATHER_SNAPSHOT_DIR: path.join(root, "data/fixture/weather"),
        FORECAST_ARTIFACT_ROOT: path.join(root, "data/fixture/forecasts"),
        ENERGY_DATA_MODE: "fixture",
        FORECAST_JOBS_ENABLED: "false",
      },
      reuseExistingServer: false,
    },
    {
      command: "npm run start -- --port 3100",
      env: { ENERGY_E2E: "1" },
      url: "http://127.0.0.1:3100",
      reuseExistingServer: false,
    },
  ],
});

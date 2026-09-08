import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";

export default defineConfig({
  testDir: "./e2e-api",
  outputDir: "./test-results/api",
  timeout: 35_000,
  expect: { timeout: 7_000 },
  fullyParallel: true,
  workers: 2,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:5175", trace: "retain-on-failure" },
  webServer: {
    command: "node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5175 --strictPort",
    env: { VITE_DATA_SOURCE: "api", VITE_API_BASE_URL: "/api/v1" },
    cwd: fileURLToPath(new URL(".", import.meta.url)),
    url: "http://127.0.0.1:5175",
    reuseExistingServer: false,
    timeout: 60_000,
  },
  projects: [{ name: "api-chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } } }],
});

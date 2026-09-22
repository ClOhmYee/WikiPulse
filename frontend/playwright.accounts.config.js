import { defineConfig } from "@playwright/test";
const port = process.env.WIKIPULSE_E2E_PORT || "5188";
export default defineConfig({
  testDir: "./e2e-accounts",
  outputDir: "./test-results/accounts",
  workers: 1,
  timeout: 45000,
  expect: { timeout: 10000 },
  use: { baseURL: `http://127.0.0.1:${port}`, trace: "retain-on-failure" },
  webServer: {
    command: `node node_modules/vite/bin/vite.js --host 127.0.0.1 --port ${port} --strictPort`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: false,
    env: {
      VITE_DATA_SOURCE: "api",
      VITE_API_BASE_URL: "/api/v1",
      VITE_API_PROXY_TARGET: process.env.ACCOUNT_E2E_BACKEND,
    },
  },
});

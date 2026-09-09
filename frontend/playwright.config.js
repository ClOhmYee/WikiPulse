import { defineConfig, devices } from '@playwright/test'
import { fileURLToPath } from 'node:url'

const port = process.env.WIKIPULSE_E2E_PORT || '5174'
const baseURL = `http://127.0.0.1:${port}`

export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  timeout: 35_000,
  expect: { timeout: 7_000 },
  fullyParallel: true,
  workers: 2,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'off',
  },
  webServer: {
    command: `node node_modules/vite/bin/vite.js --host 127.0.0.1 --port ${port} --strictPort`,
    env: { VITE_DATA_SOURCE: 'mock' },
    cwd: fileURLToPath(new URL('.', import.meta.url)),
    url: baseURL,
    reuseExistingServer: false,
    timeout: 60_000,
  },
  projects: [{
    name: 'chromium',
    use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1000 } },
  }],
})

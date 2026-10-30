import { defineConfig } from "@playwright/test";

const baseURL = process.env.LLM_BENCHMARK_UI_BASE_URL || "http://127.0.0.1:5186";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  workers: 2,
  forbidOnly: Boolean(process.env.CI),
  timeout: 45000,
  expect: { timeout: 10000 },
  outputDir: "../.tmp/evaluation-pages/browser",
  reporter: [["line"], ["json", { outputFile: "../.tmp/evaluation-pages/browser-results.json" }]],
  use: {
    baseURL,
    viewport: { width: 1440, height: 1000 },
    reducedMotion: "reduce",
    serviceWorkers: "block",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    launchOptions: { executablePath: process.env.LLM_BENCHMARK_BROWSER_PATH || undefined },
  },
  webServer: process.env.LLM_BENCHMARK_UI_BASE_URL ? undefined : {
    command: "npm run dev -- --host 127.0.0.1 --port 5186 --strictPort",
    url: baseURL,
    reuseExistingServer: false,
    timeout: 60000,
  },
});

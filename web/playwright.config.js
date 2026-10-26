import { defineConfig } from '@playwright/test'
import path from 'node:path'
process.env.PLAYWRIGHT_BROWSERS_PATH ||= path.resolve('.browsers')

export default defineConfig({
  testDir: './e2e', timeout: 60000, workers: 1, retries: 0,
  use: { baseURL: 'http://127.0.0.1:8080', viewport: { width: 1440, height: 1000 }, trace: 'retain-on-failure' },
})

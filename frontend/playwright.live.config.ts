import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./live",
  timeout: 240_000,
  retries: 0,
  use: {
    baseURL: "https://tcf-trainer.onrender.com",
    ...devices["Desktop Chrome"],
  },
});

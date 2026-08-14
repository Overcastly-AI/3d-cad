import { defineConfig } from "@playwright/test";

import base from "./playwright.config";

/** TEMPORARY (FB-20 verification): isolated Vite on :5270, no webServer. */
export default defineConfig({
  ...base,
  webServer: undefined,
  use: { ...base.use, baseURL: "http://127.0.0.1:5270" },
});

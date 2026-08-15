import path from "node:path"
import { defineConfig } from "vitest/config"

export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
    css: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
      // Mirror next.config.mjs's plotly collapse. Without these the test module
      // graph differs from production: react-plotly.js would resolve the
      // unminified `plotly.js/dist/plotly` that no longer ships, so any test
      // exercising the chart path would validate a build users never receive.
      "plotly.js/dist/plotly": "plotly.js-dist-min",
      "plotly.js/dist/plotly.js": "plotly.js-dist-min",
      "plotly.js": "plotly.js-dist-min",
    },
  },
})

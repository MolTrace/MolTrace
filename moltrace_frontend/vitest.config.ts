import path from "node:path"
import { defineConfig } from "vitest/config"

export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
    css: true,
    // The per-test timeout is a runaway detector — it exists to kill a test that
    // will never finish (an unresolved promise, a missing mock) — not a budget for
    // how long honest work may take. Vitest's 5000ms default was being spent as a
    // budget: `--run` forks `availableParallelism() - 1` workers, and the component
    // tests that mount a whole workspace slow down by 5-6x when they share a machine
    // with the other 170 files.
    //
    // Measured (2026-08-26, 8-core darwin, 171 files / 1408 tests):
    //   - The heaviest test in the suite — reaction-optimization-render.test.tsx's
    //     "Reaction Project Detail (largest workspace, 11 tabs)" — costs 785-923ms
    //     alone, but 2399-4689ms inside a full-suite run. The component is not slow;
    //     the machine is busy.
    //   - At 5000ms, 4 of 10 full-suite runs tripped, on 4 different files
    //     (reaction-optimization-render, spectracheck-ms-evidence, and under a load
    //     spike 12 tests across 8 files). It is a slow cohort, not one component.
    //   - With no reachable timeout, 5 further runs finished with zero failures:
    //     nothing here hangs, everything completes when given the CPU.
    //
    // 14411ms = the worst untruncated duration observed (4689.4ms) x 3.073, the
    // widest run-to-run spread measured on any test doing comparable work
    // (programs-interface-workspace, 1036ms -> 3185ms across identical runs). So the
    // slowest honest test would have to hit a contention spike as bad as the worst
    // one recorded, on top of its own worst recorded run, before this fires.
    // Not a round number on purpose: raise it only against a fresh measurement.
    //
    // WHAT THIS DOES NOT COVER, because the measurement behind it could not: every
    // untruncated run used to derive 4689.4ms had a healthy `transform` phase
    // (18.8-26s). It is therefore sized against CPU contention only. There is a
    // second, rarer local mode where the FILESYSTEM stalls and transform runs
    // 93-190s — 2029s once — and in that state tests still die here, because the
    // graph these tests transform inside the test body (an `await import()` in the
    // *-render suites, `next/dynamic` inside spectracheck-workspace) is charged to
    // this budget. No value fixes a 60x transform stall; the fix would be moving
    // those transforms out of the test body. Not done, because it is a local-only
    // mode: CI's transform is flat at 8.9-13.0s over 8 consecutive runs and vitest
    // has not timed out there in 30. A local run that trips this is worth re-running
    // and checking `transform` in the summary line before touching the number.
    testTimeout: 14411,
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

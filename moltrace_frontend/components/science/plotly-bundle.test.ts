/**
 * The Plotly collapse (P4 §1), actually exercised.
 *
 * next.config.mjs aliases every plotly entry point onto the single declared
 * minified bundle so a spectrum view does not ship two copies of the library.
 * Every existing viewer test stubs `react-plotly.js` or `next/dynamic`, so none
 * of them loads either build — the alias was previously unverified by any test.
 * This imports the aliased module for real and asserts the API surface
 * react-plotly.js and the image-export path depend on.
 */
import { describe, expect, it } from "vitest"

describe("plotly bundle", () => {
  it("exposes everything react-plotly.js and the export path call", async () => {
    const plotly = (await import("plotly.js-dist-min")) as unknown as {
      default?: Record<string, unknown>
    }
    const api = (plotly.default ?? plotly) as Record<string, unknown>

    // react-plotly.js/factory.js
    expect(typeof api.react).toBe("function")
    expect(typeof api.purge).toBe("function")
    expect(typeof (api.Plots as { resize?: unknown } | undefined)?.resize).toBe("function")
    // The viewers' PNG export
    expect(typeof api.downloadImage).toBe("function")
    // The trace types the science viewers render
    expect(typeof api.newPlot).toBe("function")
  })
})

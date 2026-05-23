import { describe, expect, it } from "vitest"

import {
  extractPeaksFromPayload,
  extractSpectrumXY,
} from "@/components/spectracheck/spectracheck-nmr-result-parse"

describe("extractSpectrumXY", () => {
  it("reads direct frontend preview x/y arrays", () => {
    expect(extractSpectrumXY({ x: [3.65, 1.26], y: [10, 8] })).toEqual({
      x: [3.65, 1.26],
      y: [10, 8],
    })
  })

  it("ignores intentionally omitted spectrum arrays", () => {
    expect(
      extractSpectrumXY({
        point_count: 5000,
        x: [],
        y: [],
        metadata: { spectrum_points_included: false },
      }),
    ).toBeNull()
  })

  it("reads backend preview_points rows", () => {
    expect(
      extractSpectrumXY({
        preview_points: [
          { shift_ppm: 7.26, intensity: 12 },
          { shift_ppm: 3.65, intensity: 140 },
        ],
      })
    ).toEqual({
      x: [7.26, 3.65],
      y: [12, 140],
    })
  })

  it("reads nested metadata preview_points from wrapped preview responses", () => {
    expect(
      extractSpectrumXY({
        metadata: {
          preview_points: [
            { x: 2.1, y: 3 },
            { x: 1.2, y: 5 },
          ],
        },
      })
    ).toEqual({
      x: [2.1, 1.2],
      y: [3, 5],
    })
  })

  it("reads nested preview payloads from raw FID process responses", () => {
    expect(
      extractSpectrumXY({
        preview: {
          preview_points: [
            { shift_ppm: 4.1, intensity: 30 },
            { shift_ppm: 1.2, intensity: 50 },
          ],
        },
      })
    ).toEqual({
      x: [4.1, 1.2],
      y: [30, 50],
    })
  })

  it("reads original spectrum state points from metadata", () => {
    expect(
      extractSpectrumXY({
        metadata: {
          original_spectrum_state: {
            preview_points: [
              { shift_ppm: 8.2, intensity: -1 },
              { shift_ppm: 7.9, intensity: 2 },
            ],
          },
        },
      })
    ).toEqual({
      x: [8.2, 7.9],
      y: [-1, 2],
    })
  })
})

describe("extractPeaksFromPayload", () => {
  it("returns an empty array when no peak-bearing field is present", () => {
    expect(extractPeaksFromPayload({})).toEqual([])
    expect(extractPeaksFromPayload(null)).toEqual([])
    expect(extractPeaksFromPayload("nope")).toEqual([])
  })

  it("reads ppm + intensity + label from the canonical peaks field", () => {
    const peaks = extractPeaksFromPayload({
      peaks: [
        { ppm: 7.26, intensity: 1.0, label: "Ar-H" },
        { ppm: 1.26, intensity: 0.8, label: "CH3" },
      ],
    })
    expect(peaks).toEqual([
      { ppm: 7.26, intensity: 1.0, label: "Ar-H", category: undefined },
      { ppm: 1.26, intensity: 0.8, label: "CH3", category: undefined },
    ])
  })

  it("passes the enriched category field through unchanged", () => {
    // Both the processed-analyze and raw-FID-process responses include a
    // per-peak ``category`` once enrich_peaks has run. The viewer reads it to
    // color-code markers — losing it here would silently disable category
    // colors on the chart.
    const peaks = extractPeaksFromPayload({
      peaks: [
        { ppm: 7.26, intensity: 1.0, category: "aromatic_alkene" },
        { ppm: 1.26, intensity: 0.8, category: "aliphatic" },
        { ppm: 11.5, intensity: 0.1, category: "labile_OH_NH_SH" },
      ],
    })
    expect(peaks.map((p) => p.category)).toEqual([
      "aromatic_alkene",
      "aliphatic",
      "labile_OH_NH_SH",
    ])
  })

  it("accepts shift_ppm as a synonym for ppm (raw FID payloads)", () => {
    const peaks = extractPeaksFromPayload({
      peaks: [
        { shift_ppm: 3.65, intensity: 5.0, category: "aliphatic" },
      ],
    })
    expect(peaks).toHaveLength(1)
    expect(peaks[0].ppm).toBe(3.65)
    expect(peaks[0].category).toBe("aliphatic")
  })

  it("falls back to picked_peaks / peak_table / annotations keys", () => {
    expect(
      extractPeaksFromPayload({ picked_peaks: [{ ppm: 2.0, intensity: 1 }] }),
    ).toHaveLength(1)
    expect(
      extractPeaksFromPayload({ peak_table: [{ ppm: 2.0, intensity: 1 }] }),
    ).toHaveLength(1)
    expect(
      extractPeaksFromPayload({ annotations: [{ ppm: 2.0, intensity: 1 }] }),
    ).toHaveLength(1)
  })

  it("ignores peaks with non-finite ppm but keeps the rest", () => {
    const peaks = extractPeaksFromPayload({
      peaks: [
        { ppm: 3.65, intensity: 1 },
        { ppm: null, intensity: 5 },
        { ppm: NaN, intensity: 5 },
        { ppm: 1.26, intensity: 0.8 },
      ],
    })
    expect(peaks).toHaveLength(2)
    expect(peaks.map((p) => p.ppm)).toEqual([3.65, 1.26])
  })

  it("drops empty-string categories so they fall back to the default color", () => {
    // The viewer's color lookup treats undefined as "use default" — an empty
    // string would bypass that and look up "" in the palette (miss → default
    // anyway, but the test pins the explicit-undefined behaviour).
    const peaks = extractPeaksFromPayload({
      peaks: [{ ppm: 3.65, intensity: 1, category: "" }],
    })
    expect(peaks[0].category).toBeUndefined()
  })
})

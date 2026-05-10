import { describe, expect, it } from "vitest"

import { extractSpectrumXY } from "@/components/spectracheck/spectracheck-nmr-result-parse"

describe("extractSpectrumXY", () => {
  it("reads direct frontend preview x/y arrays", () => {
    expect(extractSpectrumXY({ x: [3.65, 1.26], y: [10, 8] })).toEqual({
      x: [3.65, 1.26],
      y: [10, 8],
    })
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

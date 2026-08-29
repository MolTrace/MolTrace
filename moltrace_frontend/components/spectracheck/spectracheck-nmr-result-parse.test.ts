import { describe, expect, it } from "vitest"

import {
  extractPeaksFromPayload,
  extractSpectrumXY,
  extractNotes,
  extractRawFidArchiveFacts,
  describeReferenceMode,
  extractBaselineNoiseSigma,
  displayedDatasetName,
  extractReferenceReadout,
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

describe("extractNotes", () => {
  /**
   * `notes` is `list[str]` on every backend model that carries it, and
   * `string[]` in the generated schema — it is never a bare string. The reader
   * accepted only `typeof n === "string"`, so it returned null for every real
   * payload and the Details card's Notes block could not render at all.
   * `extractWarnings`, immediately above it in the same module, already handled
   * both shapes.
   */
  it("reads the list shape the contract actually returns", () => {
    expect(extractNotes({ notes: ["Referenced to residual solvent."] })).toBe(
      "Referenced to residual solvent.",
    )
  })

  it("joins multiple notes into the single line the card renders", () => {
    const value = extractNotes({ notes: ["First note.", "Second note."] })
    expect(value).toContain("First note.")
    expect(value).toContain("Second note.")
  })

  it("still accepts a bare string, and ignores empty or absent values", () => {
    expect(extractNotes({ note: "Single string note." })).toBe("Single string note.")
    expect(extractNotes({ notes: [] })).toBeNull()
    expect(extractNotes({ notes: ["", "   "] })).toBeNull()
    expect(extractNotes({})).toBeNull()
    expect(extractNotes(null)).toBeNull()
  })
})

describe("extractRawFidArchiveFacts", () => {
  /**
   * The results header read `raw_file_sha256`, `spectral_width_hz` and
   * `time_domain_points` off the top level of the payload. SpectrumPreviewReport
   * is `extra="forbid"` and declares none of them, so those keys could never
   * arrive and the SHA-256, spectral-width and TD tiles were permanently blank.
   */
  const realShapedPayload = {
    filename: "sample.zip",
    point_count: 9173,
    processing_metadata: {
      raw_upload_provenance: { sha256: "abc123def456" },
      acquisition_parameters: {
        sw_hz: 4800.5,
        fid_points_after_group_delay: 32768,
        sfo1_mhz: 400.13,
      },
    },
  }

  it("reads the nested shape the response models actually declare", () => {
    const facts = extractRawFidArchiveFacts(realShapedPayload)
    expect(facts.sha).toBe("abc123def456")
    expect(facts.sweepWidthHz).toBe(4800.5)
    expect(facts.fidPoints).toBe(32768)
  })

  it("returns nulls rather than throwing on an unrelated payload", () => {
    expect(extractRawFidArchiveFacts({})).toEqual({
      sha: null,
      sweepWidthHz: null,
      fidPoints: null,
    })
    expect(extractRawFidArchiveFacts(null).sha).toBeNull()
  })
})

describe("displayedDatasetName", () => {
  it("names the dataset on screen, not the one in the file input", () => {
    // The user ran "first.zip", then picked "second.zip" without running it.
    // The results still show first.zip, so that is what the header must say.
    expect(displayedDatasetName({ filename: "first.zip" }, "second.zip")).toBe("first.zip")
  })

  it("falls back to the selection before anything has run", () => {
    expect(displayedDatasetName(null, "second.zip")).toBe("second.zip")
    expect(displayedDatasetName({}, "second.zip")).toBe("second.zip")
  })

  it("returns null when neither is known", () => {
    expect(displayedDatasetName(null, null)).toBeNull()
    expect(displayedDatasetName(null, "   ")).toBeNull()
  })
})

describe("extractReferenceReadout", () => {
  it("reads the applied shift and the anchor selection off the wire", () => {
    const facts = extractReferenceReadout({
      processing_metadata: {
        reference_shift_applied_ppm: -0.024,
        reference_peak_selection: {
          observed_ppm: 7.284,
          target_ppm: 7.26,
          mode: "nearest_target_window",
        },
      },
    })
    expect(facts.shiftPpm).toBe(-0.024)
    expect(facts.observedPpm).toBe(7.284)
    expect(facts.targetPpm).toBe(7.26)
    expect(facts.mode).toBe("nearest_target_window")
  })

  it("returns nulls on a payload that carries no referencing", () => {
    expect(extractReferenceReadout({}).shiftPpm).toBeNull()
    expect(extractReferenceReadout(null).mode).toBeNull()
  })

  it("never shows a raw engine token to the reader", () => {
    // The mode distinguishes a routine solvent correction from a refusal, so it
    // has to reach the user — but as words, not as the wire value.
    expect(describeReferenceMode("nearest_target_window")).toMatch(/solvent signal/i)
    expect(describeReferenceMode("none_target_off_axis")).toMatch(/not referenced/i)
    for (const mode of ["nearest_target_window", "anomeric_window_fallback", "none_target_off_axis"]) {
      expect(describeReferenceMode(mode)).not.toContain("_")
    }
    expect(describeReferenceMode("something_new")).toBeNull()
  })
})

describe("extractBaselineNoiseSigma", () => {
  it("reads the sigma the backend measured on the undecimated trace", () => {
    expect(
      extractBaselineNoiseSigma({
        metadata: {
          display_preprocessing: { trace_smoothing: { noise_sigma: 3256.280991 } },
        },
      }),
    ).toBe(3256.280991)
  })

  it("returns undefined rather than a guess when the payload carries none", () => {
    expect(extractBaselineNoiseSigma({})).toBeUndefined()
    expect(extractBaselineNoiseSigma({ metadata: {} })).toBeUndefined()
    expect(extractBaselineNoiseSigma(null)).toBeUndefined()
    // A non-positive or non-finite sigma is no sigma at all.
    expect(
      extractBaselineNoiseSigma({
        metadata: { display_preprocessing: { trace_smoothing: { noise_sigma: 0 } } },
      }),
    ).toBeUndefined()
  })
})


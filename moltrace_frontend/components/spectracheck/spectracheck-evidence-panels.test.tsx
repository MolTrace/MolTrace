import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import {
  DP4RankingPanel,
  EnrichedPickedPeaksPanel,
  ImpurityCandidatesPanel,
  InferredNmrTextPanel,
  LabileHydrogenPanel,
  PeakCategorySummaryPanel,
  PredictedVsObservedPanel,
  ReferencesPanel,
  SpectraCheckEvidencePanels,
} from "@/components/spectracheck/spectracheck-evidence-panels"

const ENRICHED_PAYLOAD = {
  peak_count: 3,
  peaks: [
    {
      shift_ppm: 7.25,
      multiplicity: "m",
      integration_h: 5.0,
      j_values_hz: [],
      category: "aromatic_alkene",
      chemical_region: "aromatic / alkene proton",
      labile_hint: false,
      category_reason: "Shift in the 6–9 ppm aromatic/alkene window.",
      impurity_match: null,
    },
    {
      shift_ppm: 1.25,
      multiplicity: "t",
      integration_h: 3.0,
      j_values_hz: [7.0],
      category: "aliphatic",
      chemical_region: "aliphatic proton",
      labile_hint: false,
      category_reason: "Shift in the 0.5–2 ppm aliphatic window.",
      impurity_match: null,
    },
    {
      shift_ppm: 11.0,
      multiplicity: "br s",
      integration_h: 1.0,
      j_values_hz: [],
      category: "labile_OH_NH_SH",
      chemical_region: "carboxylic acid / strongly H-bonded proton",
      labile_hint: true,
      category_reason: "Broad signal in the 10–13 ppm region.",
      impurity_match: null,
    },
  ],
  peak_category_summary: { aromatic_alkene: 1, aliphatic: 1, labile_OH_NH_SH: 1 },
  impurity_candidates: [
    {
      shift_ppm: 1.55,
      integration_h: 0.3,
      reason: "matches embedded H-1 impurity shift for water (CDCl3)",
      score: 4,
      library_match: {
        label: "water (CDCl3)",
        expected_ppm: 1.56,
        delta_ppm: 0.01,
        kind: "water",
      },
    },
  ],
  labile_hydrogen_summary: {
    expected_labile_h: 1,
    observed_labile_candidates: [
      {
        shift_ppm: 11.0,
        multiplicity: "br s",
        integration_h: 1.0,
        reason: "broad downfield signal",
      },
    ],
    notes: ["Structure declares 1 labile H atom(s) (OH/NH/SH)."],
    confidence: 1.0,
  },
  predicted_vs_observed: [
    {
      status: "matched",
      predicted_ppm: 7.24,
      observed_ppm: 7.25,
      delta_ppm: 0.01,
      predicted_environment: "aromatic CH",
      observed_integration_h: 5.0,
      category: "aromatic_alkene",
    },
    {
      status: "unmatched_predicted",
      predicted_ppm: 9.50,
      observed_ppm: null,
      delta_ppm: null,
      predicted_environment: "aldehyde",
      observed_integration_h: null,
      category: null,
    },
  ],
}

describe("EnrichedPickedPeaksPanel", () => {
  it("renders shift, multiplicity, integration, J, category, region, impurity columns", () => {
    render(<EnrichedPickedPeaksPanel payload={ENRICHED_PAYLOAD} />)
    expect(screen.getByTestId("enriched-picked-peaks")).toBeInTheDocument()
    const rows = screen.getAllByTestId("enriched-peak-row")
    expect(rows).toHaveLength(3)
    // Category chips rendered
    expect(screen.getByText("Aromatic alkene")).toBeInTheDocument()
    expect(screen.getByText("Aliphatic")).toBeInTheDocument()
    expect(screen.getByText(/Labile OH \/ NH \/ SH/)).toBeInTheDocument()
    // J value column rendered
    expect(screen.getByText("7.0")).toBeInTheDocument()
  })

  it("falls back to a simple shape when enrichment is missing", () => {
    const legacy = {
      peaks: [
        { shift_ppm: 3.65, multiplicity: "q", integration_h: 2.0, j_values_hz: [] },
      ],
    }
    render(<EnrichedPickedPeaksPanel payload={legacy} />)
    expect(screen.getByTestId("enriched-picked-peaks")).toBeInTheDocument()
    // No category column header when enrichment is missing
    expect(screen.queryByText("Category")).not.toBeInTheDocument()
  })

  it("renders nothing when there are no peaks", () => {
    const { container } = render(<EnrichedPickedPeaksPanel payload={{ peaks: [] }} />)
    expect(container.firstChild).toBeNull()
  })
})

describe("InferredNmrTextPanel", () => {
  it("renders the backend-generated multiplet summary verbatim", () => {
    // The full output of the deconvolution + reference-guided multiplicity
    // pipeline must appear on screen exactly as the backend produced it — no
    // truncation, no client-side reformatting.
    const text = "5.23 (d, J = 3.6 Hz, 12.5H), 3.95 (ddd, J = 10.3, 4.6, 2.6 Hz, 9.5H)"
    render(<InferredNmrTextPanel payload={{ inferred_nmr_text: text }} />)
    expect(screen.getByTestId("inferred-nmr-text-panel")).toBeInTheDocument()
    expect(screen.getByTestId("inferred-nmr-text-body").textContent).toBe(text)
  })

  it("falls through nested preview/analysis wrappers", () => {
    // The processed-spectrum section sometimes hands the panel a payload
    // shaped ``{ preview: { inferred_nmr_text }, analysis: { inferred_nmr_text } }``
    // — prefer the analysis text and otherwise fall back to the preview.
    render(
      <InferredNmrTextPanel
        payload={{
          analysis: { inferred_nmr_text: "from analysis" },
          preview: { inferred_nmr_text: "from preview" },
        }}
      />,
    )
    expect(screen.getByTestId("inferred-nmr-text-body").textContent).toBe("from analysis")
  })

  it("renders nothing when the field is missing or empty", () => {
    const { container: empty } = render(<InferredNmrTextPanel payload={{}} />)
    expect(empty.firstChild).toBeNull()
    const { container: blank } = render(
      <InferredNmrTextPanel payload={{ inferred_nmr_text: "   " }} />,
    )
    expect(blank.firstChild).toBeNull()
  })
})

describe("PeakCategorySummaryPanel", () => {
  it("renders chips ordered by count", () => {
    render(<PeakCategorySummaryPanel payload={ENRICHED_PAYLOAD} />)
    const card = screen.getByTestId("peak-category-summary")
    expect(card).toBeInTheDocument()
    expect(screen.getByText(/Aromatic alkene · 1/)).toBeInTheDocument()
    expect(screen.getByText(/Aliphatic · 1/)).toBeInTheDocument()
  })

  it("renders nothing when the summary is empty", () => {
    const { container } = render(<PeakCategorySummaryPanel payload={{ peak_category_summary: {} }} />)
    expect(container.firstChild).toBeNull()
  })
})

describe("ImpurityCandidatesPanel", () => {
  it("renders one row per impurity candidate", () => {
    render(<ImpurityCandidatesPanel payload={ENRICHED_PAYLOAD} />)
    expect(screen.getByTestId("impurity-candidates")).toBeInTheDocument()
    const rows = screen.getAllByTestId("impurity-candidate-row")
    expect(rows).toHaveLength(1)
    expect(screen.getByText("water (CDCl3)")).toBeInTheDocument()
  })

  it("renders nothing when no impurities present", () => {
    const { container } = render(<ImpurityCandidatesPanel payload={{ impurity_candidates: [] }} />)
    expect(container.firstChild).toBeNull()
  })
})

describe("LabileHydrogenPanel", () => {
  it("renders expected/observed counts, confidence, and the candidate row", () => {
    render(<LabileHydrogenPanel payload={ENRICHED_PAYLOAD} />)
    expect(screen.getByTestId("labile-hydrogen-summary")).toBeInTheDocument()
    const row = screen.getByTestId("labile-candidate-row")
    expect(row).toBeInTheDocument()
    expect(screen.getByText(/100%/)).toBeInTheDocument()
  })

  it("renders nothing when expected=0 and no observed/notes", () => {
    const { container } = render(
      <LabileHydrogenPanel
        payload={{
          labile_hydrogen_summary: {
            expected_labile_h: 0,
            observed_labile_candidates: [],
            notes: [],
            confidence: null,
          },
        }}
      />,
    )
    expect(container.firstChild).toBeNull()
  })
})

describe("PredictedVsObservedPanel", () => {
  it("renders one row per predicted-vs-observed entry", () => {
    render(<PredictedVsObservedPanel payload={ENRICHED_PAYLOAD} />)
    expect(screen.getByTestId("predicted-vs-observed")).toBeInTheDocument()
    const rows = screen.getAllByTestId("predicted-observed-row")
    expect(rows).toHaveLength(2)
    expect(screen.getByText("matched")).toBeInTheDocument()
    expect(screen.getByText("unmatched predicted")).toBeInTheDocument()
  })

  it("renders nothing when there are no rows", () => {
    const { container } = render(<PredictedVsObservedPanel payload={{ predicted_vs_observed: [] }} />)
    expect(container.firstChild).toBeNull()
  })
})

describe("SpectraCheckEvidencePanels (composite)", () => {
  it("renders all four sub-panels when enriched payload is provided", () => {
    render(<SpectraCheckEvidencePanels payload={ENRICHED_PAYLOAD} />)
    expect(screen.getByTestId("peak-category-summary")).toBeInTheDocument()
    expect(screen.getByTestId("labile-hydrogen-summary")).toBeInTheDocument()
    expect(screen.getByTestId("impurity-candidates")).toBeInTheDocument()
    expect(screen.getByTestId("predicted-vs-observed")).toBeInTheDocument()
  })

  it("gracefully renders empty container when payload is null", () => {
    render(<SpectraCheckEvidencePanels payload={null} />)
    expect(screen.queryByTestId("peak-category-summary")).not.toBeInTheDocument()
    expect(screen.queryByTestId("impurity-candidates")).not.toBeInTheDocument()
  })
})

describe("DP4RankingPanel", () => {
  const DP4_PAYLOAD = {
    dp4_ranking: [
      {
        candidate_index: 1,
        candidate_label: "CCO",
        dp4_probability: 0.72,
        matched_peaks: 3,
        mean_abs_error_ppm: 0.05,
        rms_error_ppm: 0.07,
        scaling_slope: 1.02,
        scaling_intercept: 0.01,
        notes: [],
      },
      {
        candidate_index: 0,
        candidate_label: "CO",
        dp4_probability: 0.18,
        matched_peaks: 2,
        mean_abs_error_ppm: 0.21,
        rms_error_ppm: 0.25,
        scaling_slope: 1.0,
        scaling_intercept: 0.0,
        notes: ["Fewer than 3 paired peaks — linear scaling skipped."],
      },
    ],
  }

  it("renders a row per candidate with the DP4 probability badge", () => {
    render(<DP4RankingPanel payload={DP4_PAYLOAD} />)
    expect(screen.getByTestId("dp4-ranking")).toBeInTheDocument()
    const rows = screen.getAllByTestId("dp4-ranking-row")
    expect(rows).toHaveLength(2)
    expect(screen.getByText("72%")).toBeInTheDocument()
    expect(screen.getByText("18%")).toBeInTheDocument()
  })

  it("renders nothing when the ranking is empty", () => {
    const { container } = render(<DP4RankingPanel payload={{ dp4_ranking: [] }} />)
    expect(container.firstChild).toBeNull()
  })
})

describe("ReferencesPanel", () => {
  const REF_PAYLOAD = {
    references: [
      {
        key: "smith_goodman_2010_dp4",
        title: "Assigning the Stereochemistry of Pairs of Diastereoisomers (DP4)",
        authors: "Smith S. G.; Goodman J. M.",
        venue: "J. Am. Chem. Soc.",
        year: 2010,
        doi: "10.1021/ja105035r",
      },
      {
        key: "silverstein_2014_8e",
        title: "Spectrometric Identification of Organic Compounds (8th ed.)",
        authors: "Silverstein R. M.; Webster F. X.",
        venue: "Wiley",
        year: 2014,
      },
    ],
  }

  it("renders one entry per reference with hyperlink to DOI when present", () => {
    render(<ReferencesPanel payload={REF_PAYLOAD} />)
    expect(screen.getByTestId("references-panel")).toBeInTheDocument()
    expect(screen.getByText(/Smith S. G.; Goodman J. M./)).toBeInTheDocument()
    expect(screen.getByText(/Spectrometric Identification/)).toBeInTheDocument()
    // DOI link shape
    const doiLink = screen.getByText(/Smith S. G.; Goodman J. M./).closest("a")
    expect(doiLink).not.toBeNull()
    expect(doiLink?.getAttribute("href")).toContain("doi.org/10.1021/ja105035r")
  })

  it("renders nothing when references list is empty", () => {
    const { container } = render(<ReferencesPanel payload={{ references: [] }} />)
    expect(container.firstChild).toBeNull()
  })
})

describe("PredictedVsObservedPanel — DP4 columns", () => {
  it("shows z_DP4 and confidence chips for matched rows", () => {
    const payload = {
      predicted_vs_observed: [
        {
          status: "matched",
          predicted_ppm: 3.65,
          observed_ppm: 3.66,
          delta_ppm: 0.01,
          z_dp4: -0.05,
          tail_probability: 0.96,
          confidence: "high",
          predicted_environment: "OCH2",
        },
      ],
    }
    render(<PredictedVsObservedPanel payload={payload} />)
    expect(screen.getByText("-0.05")).toBeInTheDocument()
    expect(screen.getByText("high")).toBeInTheDocument()
  })
})

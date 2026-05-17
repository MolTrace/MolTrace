import { describe, expect, it } from "vitest"
import { render, screen, within } from "@testing-library/react"

import {
  MetadataKeyValueCard,
  ProcessingParametersCard,
} from "@/components/spectracheck/spectracheck-processing-parameters-card"

/** A representative ``processing_parameters`` block as it lands on the
 * frontend from /nmr/raw-fid/process. Mirrors
 * api.py::_processing_parameters_payload. */
const FIXTURE_PAYLOAD = {
  processing_parameters: {
    // top-level fields exposed alongside the nested dicts
    selected_preset: "balanced",
    digital_filter_correction_status: "applied",
    group_delay_correction_applied: true,
    automatic_phase_correction: true,
    automatic_baseline_correction: true,
    // nested dict that gets flattened by the card
    processing_parameters: {
      zero_fill_factor: 2,
      line_broadening_hz: 0.3,
      apodization_mode: "exponential",
    },
    phase_settings: {
      phase_mode: "auto",
      auto_phase: true,
      phase_p0: 0.0,
      phase_p1: 0.0,
    },
    baseline_correction: {
      mode: "bernstein",
      order: 3,
      lock: null,
    },
  },
}

describe("ProcessingParametersCard", () => {
  it("renders nothing when the payload has no processing_parameters block", () => {
    const { container } = render(<ProcessingParametersCard payload={{}} />)
    expect(container.firstChild).toBeNull()
  })

  it("renders a friendly card (NOT a JSON textarea) when parameters are present", () => {
    render(<ProcessingParametersCard payload={FIXTURE_PAYLOAD} />)
    const card = screen.getByTestId("processing-parameters-card")
    expect(card).toBeInTheDocument()
    // The previous implementation rendered a <textarea>; the new one must not.
    expect(card.querySelector("textarea")).toBeNull()
  })

  it("groups parameters into spectrum / phase / baseline / FID panes", () => {
    render(<ProcessingParametersCard payload={FIXTURE_PAYLOAD} />)
    expect(screen.getByTestId("processing-group-spectrum")).toBeInTheDocument()
    expect(screen.getByTestId("processing-group-phase")).toBeInTheDocument()
    expect(screen.getByTestId("processing-group-baseline")).toBeInTheDocument()
    expect(screen.getByTestId("processing-group-fid")).toBeInTheDocument()
  })

  it("formats booleans as Yes / No and renders human-readable labels", () => {
    render(<ProcessingParametersCard payload={FIXTURE_PAYLOAD} />)
    const fid = screen.getByTestId("processing-group-fid")
    // group_delay_correction_applied=true → "Group delay correction applied: Yes"
    expect(within(fid).getByText(/Group delay correction applied/i)).toBeInTheDocument()
    expect(within(fid).getByText("Yes")).toBeInTheDocument()
  })

  it("renders Phase P0 / P1 with their original numeric values", () => {
    render(<ProcessingParametersCard payload={FIXTURE_PAYLOAD} />)
    const phase = screen.getByTestId("processing-group-phase")
    expect(within(phase).getByText("Phase P0 (deg)")).toBeInTheDocument()
    expect(within(phase).getByText("Phase P1 (deg)")).toBeInTheDocument()
  })

  it("renders the apodization spectrum group with line_broadening_hz value", () => {
    render(<ProcessingParametersCard payload={FIXTURE_PAYLOAD} />)
    const spectrum = screen.getByTestId("processing-group-spectrum")
    expect(within(spectrum).getByText(/Line broadening Hz/i)).toBeInTheDocument()
    expect(within(spectrum).getByText("0.3")).toBeInTheDocument()
    expect(within(spectrum).getByText(/Zero fill factor/i)).toBeInTheDocument()
    expect(within(spectrum).getByText("2")).toBeInTheDocument()
  })

  it("surfaces unknown keys in the 'Other parameters' fallback group", () => {
    const extra = {
      processing_parameters: {
        ...FIXTURE_PAYLOAD.processing_parameters,
        novel_future_param: "some value",
      },
    }
    render(<ProcessingParametersCard payload={extra} />)
    const other = screen.getByTestId("processing-group-other")
    expect(within(other).getByText(/Novel future param/i)).toBeInTheDocument()
    expect(within(other).getByText("some value")).toBeInTheDocument()
  })
})

describe("MetadataKeyValueCard", () => {
  it("renders flat key/value rows for the acquisition_metadata dict", () => {
    const payload = {
      acquisition_metadata: {
        spectral_width_hz: 12000,
        time_domain_points: 32768,
        relaxation_delay_s: 1.5,
        nucleus: "1H",
      },
    }
    render(
      <MetadataKeyValueCard
        payload={payload}
        title="Acquisition metadata"
        field="acquisition_metadata"
        testId="acq-card"
      />,
    )
    const card = screen.getByTestId("acq-card")
    expect(card.querySelector("textarea")).toBeNull()
    expect(within(card).getByText(/Spectral width Hz/i)).toBeInTheDocument()
    expect(within(card).getByText("12000")).toBeInTheDocument()
    expect(within(card).getByText(/Time domain points/i)).toBeInTheDocument()
    expect(within(card).getByText("32768")).toBeInTheDocument()
  })

  it("renders nothing when the field is absent or empty", () => {
    const { container: empty } = render(
      <MetadataKeyValueCard payload={{}} title="X" field="acquisition_metadata" />,
    )
    expect(empty.firstChild).toBeNull()

    const { container: emptyDict } = render(
      <MetadataKeyValueCard
        payload={{ acquisition_metadata: { only_null: null, only_empty: "" } }}
        title="X"
        field="acquisition_metadata"
      />,
    )
    expect(emptyDict.firstChild).toBeNull()
  })
})

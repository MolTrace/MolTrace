import { fireEvent, render, screen, within } from "@testing-library/react"
import { useEffect } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { SpectraCheckBench } from "@/components/spectracheck/spectracheck-bench"
import {
  SpectraCheckTabStateProvider,
  useRawFidTabState,
} from "@/components/spectracheck/spectracheck-tab-state-context"
import { clearSpectraCheckRuntimeState } from "@/src/lib/spectracheck/spectracheck-runtime-reset"
import type { RawFidBatchItem } from "@/src/lib/spectracheck/raw-fid-batch"

/** Capture what the canvas receives — jsdom never renders Plotly, so props are the ground truth. */
const viewer = vi.hoisted(() => ({ received: [] as Array<{ pointCount: number }> }))

vi.mock("@/components/science/SpectrumViewer", () => ({
  SpectrumViewer: (props: { x: number[] }) => {
    viewer.received.push({ pointCount: props.x.length })
    return <div data-testid="bench-spectrum" data-point-count={props.x.length} />
  },
}))

function doneItem(id: string, label: string, pointCount: number): RawFidBatchItem {
  const x: number[] = []
  const y: number[] = []
  for (let i = 0; i < pointCount; i++) {
    x.push(10 - (i / (pointCount - 1)) * 10)
    y.push(i === Math.floor(pointCount / 2) ? 90 : 1)
  }
  return {
    id,
    file: new File(["fid"], `${label}.zip`),
    label,
    sourceDir: null,
    fileCount: null,
    uncompressedBytes: null,
    status: "done",
    mode: "process",
    error: null,
    startedAt: null,
    durationMs: 1200,
    result: {
      vendor_detected: "Bruker 1D",
      nucleus: "1H",
      point_count: pointCount,
      x,
      y,
      peaks: [{ shift_ppm: 7.2 }, { shift_ppm: 3.4 }],
      processing_parameters: { selected_preset: "safe_automatic" },
      metadata: {},
      warnings: [],
    },
  }
}

/** Seed the shared tab state the way the queue would have left it. */
function Seed({ items, activeId }: { items: RawFidBatchItem[]; activeId?: string }) {
  const { update } = useRawFidTabState()
  useEffect(() => {
    update({ batchItems: items, batchActiveId: activeId ?? null })
    // Seed exactly once — deps deliberately empty.
  }, [])

  return null
}

function renderBench(items: RawFidBatchItem[], activeId?: string) {
  return render(
    <SpectraCheckTabStateProvider>
      <Seed items={items} activeId={activeId} />
      <SpectraCheckBench />
    </SpectraCheckTabStateProvider>,
  )
}

beforeEach(() => {
  clearSpectraCheckRuntimeState()
  viewer.received.length = 0
  window.localStorage.removeItem("moltrace:bench-layout:v1")
  window.localStorage.removeItem("moltrace:bench-canvas:v1")
})

describe("the Evidence Bench", () => {
  it("shows the queue, the spectrum, and the peak table at the same time", () => {
    renderBench([doneItem("a", "Study/2", 256), doneItem("b", "Study/6", 128)])

    // All three regions co-visible — the whole point of the Bench.
    const rail = screen.getByLabelText("Datasets")
    expect(within(rail).getByText("Study/2")).toBeInTheDocument()
    expect(within(rail).getByText("Study/6")).toBeInTheDocument()
    expect(screen.getByTestId("bench-spectrum")).toBeInTheDocument()
    expect(screen.getByLabelText("Inspector")).toBeInTheDocument()
    // The recipe rail names what produced the numbers.
    expect(screen.getByLabelText("Processing recipe")).toBeInTheDocument()
  })

  it("selects a dataset through the SAME state the queue highlights", () => {
    renderBench([doneItem("a", "Study/2", 256), doneItem("b", "Study/6", 128)], "a")

    expect(screen.getByTestId("bench-source-a")).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByTestId("bench-spectrum")).toHaveAttribute("data-point-count", "256")

    fireEvent.click(screen.getByTestId("bench-source-b"))

    expect(screen.getByTestId("bench-source-b")).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByTestId("bench-source-a")).toHaveAttribute("aria-pressed", "false")
    // The canvas follows the selection — dataset b's trace, not a's.
    expect(screen.getByTestId("bench-spectrum")).toHaveAttribute("data-point-count", "128")
  })

  it("cycles pane focus with F6 and back with Shift+F6", () => {
    renderBench([doneItem("a", "Study/2", 64)])
    const bench = screen.getByTestId("spectracheck-bench")

    fireEvent.keyDown(bench, { key: "F6" })
    expect(document.activeElement).toBe(screen.getByLabelText("Datasets"))

    fireEvent.keyDown(bench, { key: "F6" })
    expect(document.activeElement).toBe(screen.getByLabelText("Spectrum canvas"))

    fireEvent.keyDown(bench, { key: "F6", shiftKey: true })
    expect(document.activeElement).toBe(screen.getByLabelText("Datasets"))
  })

  it("offers resize handles with the separator role, so panes are keyboard-adjustable", () => {
    renderBench([doneItem("a", "Study/2", 64)])
    expect(screen.getAllByRole("separator").length).toBeGreaterThanOrEqual(3)
  })

  it("sends an empty bench to the Raw FID section through the deep-link contract", () => {
    renderBench([])
    const link = within(screen.getByTestId("bench-empty")).getByRole("link", {
      name: /Raw FID upload/i,
    })
    expect(link).toHaveAttribute("href", "/spectracheck?section=tab-raw-fid")
  })
})

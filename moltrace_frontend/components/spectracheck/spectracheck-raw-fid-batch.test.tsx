import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import type { ReactElement } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError, apiFetch } from "@/lib/api/client"
import { SpectraCheckRawFidSection } from "@/components/spectracheck/spectracheck-raw-fid-section"
import { SpectraCheckEvidenceProvider } from "@/src/lib/spectracheck/useSpectraCheckEvidence"
import { clearSpectraCheckRuntimeState } from "@/src/lib/spectracheck/spectracheck-runtime-reset"
import { SpectraCheckTabStateProvider } from "@/components/spectracheck/spectracheck-tab-state-context"
import { stackTraceColor } from "@/components/science/SpectrumStackViewer"
import { allowConsole } from "@/src/test/setup"

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>("@/lib/api/client")
  return { ...actual, apiFetch: vi.fn() }
})

vi.mock("@/components/science/SpectrumViewer", () => ({
  SpectrumViewer: (props: { nucleus?: string; peaks?: unknown[] }) => (
    <div data-testid="spectrum-viewer" data-peak-count={props.peaks?.length ?? 0} />
  ),
}))

const apiFetchMock = vi.mocked(apiFetch)

function renderSection(): ReturnType<typeof render> {
  const ui: ReactElement = (
    <SpectraCheckRawFidSection sampleId="sample-1" onSampleIdChange={() => {}} solvent="CDCl3" />
  )
  return render(<SpectraCheckEvidenceProvider>{ui}</SpectraCheckEvidenceProvider>)
}

function archive(name: string): File {
  return new File(["fid-bytes"], name, { type: "application/zip" })
}

/** A minimal process response with a spectrum, so a row can reach "done" and be stacked. */
function processResponse(overrides: Record<string, unknown> = {}) {
  const x: number[] = []
  const y: number[] = []
  for (let i = 0; i < 64; i++) {
    x.push(i / 8)
    y.push(i === 30 ? 100 : 1)
  }
  return {
    sample_id: "sample-1",
    vendor_detected: "bruker",
    nucleus: "1H",
    point_count: 64,
    x,
    y,
    peaks: [{ shift_ppm: 3.75 }, { shift_ppm: 1.2 }],
    warnings: [],
    metadata: {},
    ...overrides,
  }
}

/** Drop archives onto the raw-FID zone. jsdom has no DataTransfer, so hand-roll the payload. */
function dropArchives(files: File[]) {
  fireEvent.drop(screen.getByRole("button", { name: /Drop raw FID archive/i }), {
    dataTransfer: { files, types: ["Files"] },
  })
}

/**
 * Calls to the two analysis routes only.
 *
 * Once a processed result renders, the run-review panel below fires its own request. Counting
 * raw mock calls would fold that in and make "one dataset at a time" look violated.
 */
function analysisCalls() {
  return apiFetchMock.mock.calls.filter((call) => String(call[0]).startsWith("/nmr/raw-fid/"))
}

/** Route by path so the run-review panel's request never consumes an analysis fixture. */
function routeAnalysis(next: () => unknown) {
  apiFetchMock.mockImplementation(async (path: string) => {
    if (String(path).startsWith("/nmr/raw-fid/")) return next() as never
    // Anything else on screen (the run list under the results) gets an empty answer.
    return [] as never
  })
}

/** Answer the analysis routes from a list, in order; everything else gets an empty answer. */
function routeAnalysisSequence(steps: Array<() => unknown>) {
  let index = 0
  apiFetchMock.mockImplementation(async (path: string) => {
    if (!String(path).startsWith("/nmr/raw-fid/")) return [] as never
    const step = steps[Math.min(index, steps.length - 1)]
    index += 1
    return step() as never
  })
}

/** jsdom reports style colours as rgb(); the palette is authored as hex. */
function asRgb(hex: string): string {
  const value = hex.replace("#", "")
  const n = parseInt(value, 16)
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`
}

/** Never resolves until the test says so — lets a run be inspected mid-flight. */
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  clearSpectraCheckRuntimeState()
  apiFetchMock.mockReset()
})

describe("queueing several datasets", () => {
  it("makes a row per dropped archive instead of keeping only the last one", () => {
    renderSection()
    dropArchives([archive("expt-33.zip"), archive("expt-34.zip"), archive("expt-35.zip")])

    expect(screen.getByTestId("raw-fid-queue")).toBeInTheDocument()
    expect(screen.getByText("expt-33.zip")).toBeInTheDocument()
    expect(screen.getByText("expt-34.zip")).toBeInTheDocument()
    expect(screen.getByText("expt-35.zip")).toBeInTheDocument()
    expect(screen.getByText(/Dataset queue · 3/)).toBeInTheDocument()
  })

  it("accepts a multi-file pick from the archive picker", () => {
    const { container } = renderSection()
    const input = container.querySelector("#raw-file") as HTMLInputElement
    expect(input.multiple).toBe(true)

    fireEvent.change(input, { target: { files: [archive("a.zip"), archive("b.zip")] } })
    expect(screen.getByText("a.zip")).toBeInTheDocument()
    expect(screen.getByText("b.zip")).toBeInTheDocument()
  })

  it("shows no queue at all until something is dropped, so a single upload is unchanged", () => {
    renderSection()
    expect(screen.queryByTestId("raw-fid-queue")).not.toBeInTheDocument()
  })

  it("turns away a file that is not an archive, with a reason, instead of failing later", () => {
    renderSection()
    dropArchives([archive("good.zip"), new File(["x"], "notes.csv")])

    expect(within(screen.getByTestId("raw-fid-queue-table")).getByText("notes.csv")).toBeInTheDocument()
    expect(within(screen.getByTestId("raw-fid-queue-errors")).getByText(/not a recognised archive/i)).toBeInTheDocument()
    // The refused row is not counted as work to do.
    expect(screen.getByTestId("raw-fid-queue-run-all")).toHaveTextContent("1 dataset")
  })

  it("removes one dataset without disturbing the rest", () => {
    renderSection()
    dropArchives([archive("a.zip"), archive("b.zip")])
    const row = screen.getByText("a.zip").closest("tr") as HTMLElement
    fireEvent.click(within(row).getByRole("button", { name: /Remove a\.zip/i }))

    expect(screen.queryByText("a.zip")).not.toBeInTheDocument()
    expect(screen.getByText("b.zip")).toBeInTheDocument()
  })

  it("empties the queue on demand", () => {
    renderSection()
    dropArchives([archive("a.zip"), archive("b.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-clear"))
    expect(screen.queryByTestId("raw-fid-queue")).not.toBeInTheDocument()
  })
})

describe("running the queue", () => {
  it("analyzes every dataset, ONE AT A TIME", async () => {
    const first = deferred<unknown>()
    const second = deferred<unknown>()
    routeAnalysisSequence([() => first.promise, () => second.promise])

    renderSection()
    dropArchives([archive("a.zip"), archive("b.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))

    // Only the first request is out — the second must wait for it.
    await waitFor(() => expect(analysisCalls()).toHaveLength(1))
    expect(analysisCalls()[0][0]).toBe("/nmr/raw-fid/process")

    await act(async () => {
      first.resolve(processResponse())
    })
    await waitFor(() => expect(analysisCalls()).toHaveLength(2))

    await act(async () => {
      second.resolve(processResponse())
    })
    await waitFor(() => expect(screen.getAllByText("Done")).toHaveLength(2))
  })

  it("sends each dataset's own archive, not the same one twice", async () => {
    routeAnalysis(() => processResponse())
    renderSection()
    dropArchives([archive("a.zip"), archive("b.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))

    await waitFor(() => expect(analysisCalls()).toHaveLength(2))
    const names = analysisCalls().map((call) => {
      const body = (call[1] as { body: FormData }).body
      return (body.get("file") as File).name
    })
    expect(names).toEqual(["a.zip", "b.zip"])
  })

  it("runs a quick scan against the preview analysis when that mode is chosen", async () => {
    routeAnalysis(() => processResponse())
    renderSection()
    dropArchives([archive("a.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-mode-scan"))
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/nmr/raw-fid/preview", expect.any(Object)))
  })

  it("freezes the run settings so a control nudged mid-run does not split the batch", async () => {
    const first = deferred<unknown>()
    routeAnalysisSequence([() => first.promise, () => processResponse()])

    renderSection()
    dropArchives([archive("a.zip"), archive("b.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))
    await waitFor(() => expect(analysisCalls()).toHaveLength(1))

    // Switch nucleus while the first dataset is still in flight.
    fireEvent.click(screen.getByRole("button", { name: "13C" }))
    await act(async () => {
      first.resolve(processResponse())
    })
    await waitFor(() => expect(analysisCalls()).toHaveLength(2))

    const nuclei = analysisCalls().map((call) => (call[1] as { body: FormData }).body.get("nucleus"))
    expect(nuclei).toEqual(["1H", "1H"])
  })

  it("stops the run on request and leaves the untouched datasets runnable", async () => {
    const first = deferred<unknown>()
    routeAnalysisSequence([() => first.promise])

    renderSection()
    dropArchives([archive("a.zip"), archive("b.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))
    await waitFor(() => expect(analysisCalls()).toHaveLength(1))

    // The signal the section passes is what a real cancellation would abort.
    const signal = (analysisCalls()[0][1] as { signal?: AbortSignal }).signal
    expect(signal).toBeInstanceOf(AbortSignal)

    fireEvent.click(screen.getByTestId("raw-fid-queue-stop"))
    expect(signal?.aborted).toBe(true)

    await act(async () => {
      first.reject(new DOMException("aborted", "AbortError"))
    })
    await waitFor(() => expect(screen.getByText("Stopped")).toBeInTheDocument())
    // The second dataset was never sent, and is still waiting.
    expect(analysisCalls()).toHaveLength(1)
    expect(screen.getByText("Queued")).toBeInTheDocument()
  })

  it("keeps going past a dataset that fails on its own merits", async () => {
    allowConsole("error")
    routeAnalysisSequence([
      () => Promise.reject(new ApiError(400, { detail: "unreadable" }, "That archive could not be read.")),
      () => processResponse(),
    ])

    renderSection()
    dropArchives([archive("bad.zip"), archive("good.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))

    await waitFor(() => expect(screen.getByText("Failed")).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText("Done")).toBeInTheDocument())
    expect(analysisCalls()).toHaveLength(2)
  })

  it("does NOT call a timed-out dataset failed, and says its run was kept", async () => {
    allowConsole("error")
    routeAnalysisSequence([
      () => Promise.reject(new ApiError(504, { detail: "gateway" }, "Could not reach the MolTrace service.")),
    ])

    renderSection()
    dropArchives([archive("slow.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))

    await waitFor(() => expect(screen.getByText("Unconfirmed")).toBeInTheDocument())
    expect(screen.getByText(/still being analyzed/i)).toBeInTheDocument()
    expect(screen.queryByText("Failed")).not.toBeInTheDocument()
  })

  it("stops the whole run on a refusal that would repeat for every dataset", async () => {
    allowConsole("error")
    routeAnalysisSequence([() => Promise.reject(new ApiError(403, { detail: "nope" }, "You do not have access."))])

    renderSection()
    dropArchives([archive("a.zip"), archive("b.zip"), archive("c.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))

    await waitFor(() => expect(screen.getByText("Run stopped")).toBeInTheDocument())
    // One attempt, not three.
    expect(analysisCalls()).toHaveLength(1)
  })

  it("re-runs a single dataset without touching the others", async () => {
    allowConsole("error")
    routeAnalysisSequence([() => Promise.reject(new ApiError(400, {}, "Could not be read."))])

    renderSection()
    dropArchives([archive("a.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))
    await waitFor(() => expect(screen.getByText("Failed")).toBeInTheDocument())

    routeAnalysisSequence([() => processResponse()])
    fireEvent.click(screen.getByRole("button", { name: /^Process a\.zip$/i }))
    await waitFor(() => expect(screen.getByText("Done")).toBeInTheDocument())
  })
})

describe("a finished dataset feeds the analysis below", () => {
  it("selects the first finished dataset so results appear without another click", async () => {
    routeAnalysis(() => processResponse())
    renderSection()
    dropArchives([archive("a.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))

    expect(await screen.findByText(/Processed FID output/i)).toBeInTheDocument()
    expect(screen.getByTestId("spectrum-viewer")).toHaveAttribute("data-peak-count", "2")
  })

  it("swaps the whole results surface when another dataset is chosen", async () => {
    routeAnalysisSequence([
      () => processResponse({ peaks: [{ shift_ppm: 1 }] }),
      () => processResponse({ peaks: [{ shift_ppm: 1 }, { shift_ppm: 2 }, { shift_ppm: 3 }] }),
    ])

    renderSection()
    dropArchives([archive("a.zip"), archive("b.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))
    await waitFor(() => expect(screen.getAllByText("Done")).toHaveLength(2))

    // The first result is on screen; choosing the second replaces it.
    expect(screen.getByTestId("spectrum-viewer")).toHaveAttribute("data-peak-count", "1")
    const secondRow = within(screen.getByTestId("raw-fid-queue-table"))
      .getByText("b.zip")
      .closest("tr") as HTMLElement
    fireEvent.click(within(secondRow).getByRole("button", { pressed: false }))
    await waitFor(() =>
      expect(screen.getByTestId("spectrum-viewer")).toHaveAttribute("data-peak-count", "3"),
    )
  })

  it("stacks every finished spectrum together once there are two to compare", async () => {
    routeAnalysis(() => processResponse())
    renderSection()
    dropArchives([archive("a.zip"), archive("b.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))

    await waitFor(() => expect(screen.getByTestId("raw-fid-queue-stack")).toBeInTheDocument())
    expect(screen.getByText(/Stacked comparison · 2 spectra/)).toBeInTheDocument()
  })

  it("does not offer a comparison of a single spectrum", async () => {
    routeAnalysis(() => processResponse())
    renderSection()
    dropArchives([archive("a.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))

    await waitFor(() => expect(screen.getByText("Done")).toBeInTheDocument())
    expect(screen.queryByTestId("raw-fid-queue-stack")).not.toBeInTheDocument()
  })
})

describe("a run outliving the tab it was started from", () => {
  /** The workspace drops an inactive tab's contents, so the section really does unmount. */
  function Frame({ showRaw }: { showRaw: boolean }) {
    return (
      <SpectraCheckTabStateProvider>
        <SpectraCheckEvidenceProvider>
          {showRaw ? (
            <SpectraCheckRawFidSection sampleId="sample-1" onSampleIdChange={() => {}} solvent="CDCl3" />
          ) : (
            <p>another tab</p>
          )}
        </SpectraCheckEvidenceProvider>
      </SpectraCheckTabStateProvider>
    )
  }

  it("keeps working while the user is on another tab, and shows the result on return", async () => {
    const first = deferred<unknown>()
    routeAnalysisSequence([() => first.promise, () => processResponse()])

    const { rerender } = render(<Frame showRaw />)
    dropArchives([archive("a.zip"), archive("b.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))
    await waitFor(() => expect(analysisCalls()).toHaveLength(1))

    // Leave the tab. The section unmounts; the run does not.
    rerender(<Frame showRaw={false} />)
    expect(screen.queryByTestId("raw-fid-queue")).not.toBeInTheDocument()

    await act(async () => {
      first.resolve(processResponse())
    })
    await waitFor(() => expect(analysisCalls()).toHaveLength(2))

    // Come back: both datasets are there, finished, with nothing lost.
    rerender(<Frame showRaw />)
    await waitFor(() => expect(screen.getAllByText("Done")).toHaveLength(2))
    const table = within(screen.getByTestId("raw-fid-queue-table"))
    expect(table.getByText("a.zip")).toBeInTheDocument()
    expect(table.getByText("b.zip")).toBeInTheDocument()
  })

  it("will not start a second run on top of one already going", async () => {
    const first = deferred<unknown>()
    routeAnalysisSequence([() => first.promise, () => processResponse()])

    const { rerender } = render(<Frame showRaw />)
    dropArchives([archive("a.zip"), archive("b.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))
    await waitFor(() => expect(analysisCalls()).toHaveLength(1))

    // A tab round-trip remounts the section — it must come back knowing a run is in flight.
    rerender(<Frame showRaw={false} />)
    rerender(<Frame showRaw />)
    expect(screen.getByTestId("raw-fid-queue-stop")).toBeInTheDocument()
    expect(screen.queryByTestId("raw-fid-queue-run-all")).not.toBeInTheDocument()

    await act(async () => {
      first.resolve(processResponse())
    })
    await waitFor(() => expect(analysisCalls()).toHaveLength(2))
    // Two datasets, two requests — the remount did not duplicate the work.
    expect(analysisCalls()).toHaveLength(2)
  })

  it("does not strand the queue when the user leaves the workspace mid-run", async () => {
    // This request never settles, so the run is still holding its claim at the moment the
    // workspace goes away — the exact state that used to leak.
    const stalled = deferred<unknown>()
    routeAnalysisSequence([() => stalled.promise, () => processResponse()])

    const { unmount } = render(<Frame showRaw />)
    dropArchives([archive("a.zip"), archive("b.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))
    await waitFor(() => expect(analysisCalls()).toHaveLength(1))

    // Leave SpectraCheck altogether: the provider holding the queue state unmounts, so every
    // write the run makes from here lands somewhere nobody can see.
    unmount()

    // Come back. The rows survive (the runtime cache carries them) and the interrupted one reads
    // as stopped rather than still running.
    render(<Frame showRaw />)
    await waitFor(() => expect(screen.getByTestId("raw-fid-queue-table")).toBeInTheDocument())
    expect(screen.getByTestId("raw-fid-queue-run-all")).toBeInTheDocument()

    // The claim was released on the way out, so this actually runs. Before that fix the run
    // button was present but inert, and stayed inert for as long as the stranded run lived.
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))
    await waitFor(() => expect(analysisCalls().length).toBeGreaterThan(1))
  })
})

describe("one dataset's analysis is never shown beside another's spectrum", () => {
  it("drops the experimental peak analysis when the reviewer moves to another dataset", async () => {
    routeAnalysisSequence([() => processResponse(), () => processResponse()])
    renderSection()
    dropArchives([archive("a.zip"), archive("b.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))
    await waitFor(() => expect(screen.getAllByText("Done")).toHaveLength(2))

    // Run the experimental analysis against the first dataset.
    apiFetchMock.mockImplementation(async (path: string) => {
      if (String(path) === "/spectrum/analyze/gsd") {
        return { peaks: [{ position_ppm: 7.26, intensity: 10 }], backend: "gsd_prompt3" } as never
      }
      return [] as never
    })
    fireEvent.click(screen.getByRole("radio", { name: "GSD" }))
    fireEvent.click(screen.getByRole("button", { name: /Run GSD analysis/i }))
    await waitFor(() => expect(screen.getByTestId("raw-fid-gsd-results-surface")).toBeInTheDocument())

    // Move to the other dataset: the previous dataset's analysis must not stay on screen.
    const secondRow = within(screen.getByTestId("raw-fid-queue-table"))
      .getByText("b.zip")
      .closest("tr") as HTMLElement
    fireEvent.click(within(secondRow).getByRole("button", { pressed: false }))

    await waitFor(() =>
      expect(screen.queryByTestId("raw-fid-gsd-results-surface")).not.toBeInTheDocument(),
    )
  })
})

describe("queue copy", () => {
  it("says why datasets run one at a time, without implementation language", () => {
    renderSection()
    dropArchives([archive("a.zip")])
    const queue = screen.getByTestId("raw-fid-queue")
    expect(queue).toHaveTextContent(/one at a time/i)
    expect(queue.textContent ?? "").not.toMatch(/POST |http|backend|_json|endpoint|\b4\d\d\b/i)
  })
})

describe("analysis stays bound to the dataset it was run on", () => {
  it("drops the experimental analysis when a newly processed archive replaces the surface", async () => {
    // The reset used to key on the queue SELECTION alone. Processing a freshly attached archive
    // swaps the whole results surface without changing the selection, so dataset a's peak table,
    // multiplets and J-couplings stayed on screen under dataset b's spectrum.
    routeAnalysisSequence([() => processResponse(), () => processResponse({ point_count: 128 })])
    renderSection()
    dropArchives([archive("a.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))
    await waitFor(() => expect(screen.getByText("Done")).toBeInTheDocument())

    apiFetchMock.mockImplementation(async (path: string) => {
      if (String(path) === "/spectrum/analyze/gsd") {
        return { peaks: [{ position_ppm: 7.26, intensity: 10 }], backend: "gsd_prompt3" } as never
      }
      if (String(path).startsWith("/nmr/raw-fid/")) return processResponse({ point_count: 128 }) as never
      return [] as never
    })
    fireEvent.click(screen.getByRole("radio", { name: "GSD" }))
    fireEvent.click(screen.getByRole("button", { name: /Run GSD analysis/i }))
    await waitFor(() => expect(screen.getByTestId("raw-fid-gsd-results-surface")).toBeInTheDocument())

    // Attach a DIFFERENT archive and process it from the single-dataset controls. The queue
    // selection never changes, but the spectrum on screen does.
    fireEvent.click(screen.getByRole("radio", { name: /Legacy/ }))
    dropArchives([archive("b.zip")])
    fireEvent.click(screen.getByRole("button", { name: /Process FID/i }))

    await waitFor(() =>
      expect(screen.queryByTestId("raw-fid-gsd-results-surface")).not.toBeInTheDocument(),
    )
  })

  it("gives a row the same colour as its line in the stacked plot", async () => {
    // Colour is the only thing linking a table row to a trace. The table used to colour by row
    // index while the plot coloured by position among DRAWN traces, so any row that produced no
    // line — still queued, failed, or finished with no spectrum — shifted every colour after it.
    routeAnalysisSequence([
      () => processResponse({ x: [], y: [], point_count: 0 }),
      () => processResponse(),
    ])
    renderSection()
    dropArchives([archive("no-trace.zip"), archive("has-trace.zip")])
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))
    await waitFor(() => expect(screen.getAllByText("Done")).toHaveLength(2))

    const rows = within(screen.getByTestId("raw-fid-queue-table"))
    const dotOf = (label: string) => {
      const row = rows.getByText(label).closest("tr") as HTMLElement
      return (row.querySelector("span[aria-hidden]") as HTMLElement).style.backgroundColor
    }

    // The first row produced no spectrum, so it owns no colour in the stack...
    expect(dotOf("no-trace.zip")).toBe("var(--mt-slate)")
    // ...and the one that DID draw wears the first stack colour, not the second. Keyed off the
    // exported palette so the test tracks the plot rather than restating a hex value.
    expect(dotOf("has-trace.zip")).toBe(asRgb(stackTraceColor(0)))
  })
})

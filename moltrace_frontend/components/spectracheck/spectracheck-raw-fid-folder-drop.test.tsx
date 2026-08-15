/**
 * Drives a real instrument-folder DROP through the raw-FID uploader, end to end: the drop event,
 * the directory walk, the split into one archive per experiment, the queue rows, and the readout
 * of what the instrument recorded.
 *
 * The drop path had no test at this level. Its pieces were covered — `vendor-folder-drop` unit
 * tests for the walk and the split — but nothing exercised the one thing that can only fail in
 * the browser: `webkitGetAsEntry` must be called while the drop event is still on the stack, so
 * an `await` in the wrong place turns a working folder drop into a silent no-op that no unit test
 * would ever see.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import type { ReactElement } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { apiFetch } from "@/lib/api/client"
import { SpectraCheckRawFidSection } from "@/components/spectracheck/spectracheck-raw-fid-section"
import { SpectraCheckEvidenceProvider } from "@/src/lib/spectracheck/useSpectraCheckEvidence"

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>("@/lib/api/client")
  return { ...actual, apiFetch: vi.fn() }
})

vi.mock("@/components/science/SpectrumViewer", () => ({
  SpectrumViewer: () => <div data-testid="spectrum-viewer" />,
}))

const apiFetchMock = vi.mocked(apiFetch)

function renderSection(solvent = "CDCl3"): ReturnType<typeof render> {
  const ui: ReactElement = (
    <SpectraCheckRawFidSection sampleId="sample-1" onSampleIdChange={() => {}} solvent={solvent} />
  )
  return render(<SpectraCheckEvidenceProvider>{ui}</SpectraCheckEvidenceProvider>)
}

/** Format-accurate synthetic parameter files — see vendor-acquisition.test.ts for why synthetic. */
const acqus = (nucleus: string, solvent = "CDCl3") =>
  [
    "##TITLE= Parameter file",
    "##$BF1= 400.1300000",
    `##$NUC1= <${nucleus}>`,
    "##$NUC2= <off>",
    "##$SFO1= 400.1324710",
    `##$SOLVENT= <${solvent}>`,
    "##END=",
  ].join("\n")

const procpar = (nucleus: string, solvent = "cdcl3") =>
  [
    "sfrq 1 1 0 0 1 1 1 1 1 64",
    "1 399.7439253",
    "0",
    "solvent 2 2 6 0 0 2 1 11 1 64",
    `1 "${solvent}"`,
    "0",
    "tn 2 2 4 0 0 2 1 8 1 64",
    `1 "${nucleus}"`,
    "0",
  ].join("\n")

type Tree = { [name: string]: string | Tree }

/**
 * A stand-in for the browser's FileSystemEntry API, which jsdom does not implement.
 *
 * `readEntries` is deliberately drained in BATCHES OF TWO and returns [] when exhausted, because
 * the real API caps a call at about 100 entries and returning everything at once would let a
 * reader that forgets to loop pass. That is the defect most likely to reach production here: it
 * only shows up on a folder with more than 100 files, which is exactly the folder a real
 * instrument writes and never the one a developer tests with.
 */
function makeDirectoryEntry(name: string, tree: Tree): FileSystemDirectoryEntry {
  const children = Object.entries(tree).map(([childName, value]) =>
    typeof value === "string"
      ? ({
          isFile: true,
          isDirectory: false,
          name: childName,
          file: (cb: (f: File) => void) => cb(new File([value], childName)),
        } as unknown as FileSystemEntry)
      : (makeDirectoryEntry(childName, value) as unknown as FileSystemEntry),
  )
  return {
    isFile: false,
    isDirectory: true,
    name,
    createReader: () => {
      let cursor = 0
      return {
        readEntries: (cb: (entries: FileSystemEntry[]) => void) => {
          const batch = children.slice(cursor, cursor + 2)
          cursor += batch.length
          cb(batch)
        },
      }
    },
  } as unknown as FileSystemDirectoryEntry
}

/** Fire a drop carrying a directory, the way a browser delivers one. */
function dropFolder(name: string, tree: Tree, alongside: File[] = []) {
  const entry = makeDirectoryEntry(name, tree)
  fireEvent.drop(screen.getByRole("button", { name: /Drop raw FID archive/i }), {
    dataTransfer: {
      // dataTransfer.files lists the folder itself plus any loose archives — the component has to
      // filter it, or the folder shows up as a bogus unusable row.
      files: [new File([], name), ...alongside],
      types: ["Files"],
      items: [
        { kind: "file", webkitGetAsEntry: () => entry },
        ...alongside.map((f) => ({
          kind: "file",
          webkitGetAsEntry: () => ({ isFile: true, isDirectory: false, name: f.name }),
        })),
      ],
    },
  })
}

const readout = () => screen.queryByTestId("raw-fid-acquisition-readout")

/** Which pill is currently selected — the toggle marks the active one with the brand fill. */
function selectedNucleus(): string | null {
  for (const label of ["1H", "13C"]) {
    const button = screen.getByRole("button", { name: label })
    if (button.getAttribute("style")?.includes("--mt-teal")) return label
  }
  return null
}

beforeEach(() => {
  apiFetchMock.mockReset()
})

describe("dropping an instrument folder", () => {
  it("walks the folder, splits every experiment out, and queues them all", async () => {
    renderSection()
    dropFolder("Sample", {
      "1": { fid: "binary", acqus: acqus("1H") },
      "2": { fid: "binary", acqus: acqus("1H") },
      "10": { fid: "binary", acqus: acqus("1H") },
    })

    // Three experiments become three datasets. One combined archive would have been worse than a
    // convenience loss: the analyzer keeps only the best-scoring dataset per archive, so the other
    // two would have been silently invisible.
    await waitFor(() => {
      expect(screen.getByText("Sample/1")).toBeInTheDocument()
      expect(screen.getByText("Sample/2")).toBeInTheDocument()
      expect(screen.getByText("Sample/10")).toBeInTheDocument()
    })
  })

  it("reads nucleus, solvent and vendor off the files and moves the toggle", async () => {
    renderSection()
    // The form opens on 1H; this folder is carbon, and before this readout existed the only way
    // to find that out was to process it.
    expect(selectedNucleus()).toBe("1H")

    dropFolder("Sample", { "1": { fid: "binary", acqus: acqus("13C") } })

    await waitFor(() => expect(readout()).toBeInTheDocument())
    expect(readout()).toHaveTextContent("13C")
    expect(readout()).toHaveTextContent("CDCl3")
    expect(readout()).toHaveTextContent("Bruker")
    // The analyzer already prefers NUC1 over the requested nucleus, so moving the toggle reports
    // a decision that has effectively already been made rather than making a new one.
    await waitFor(() => expect(selectedNucleus()).toBe("13C"))
  })

  it("recognises a Varian/Agilent folder and its own spelling of carbon", async () => {
    renderSection()
    dropFolder("Sample", { "1": { fid: "binary", procpar: procpar("C13") } })

    await waitFor(() => expect(readout()).toBeInTheDocument())
    expect(readout()).toHaveTextContent("Varian/Agilent")
    // Varian writes "C13" where Bruker writes "13C". Unnormalized it would match neither pill.
    await waitFor(() => expect(selectedNucleus()).toBe("13C"))
  })

  it("leaves the toggle alone for a mixed 1H/13C folder and says why", async () => {
    renderSection()
    // Moved OFF the default first. Asserting the toggle still reads 1H afterwards would pass just
    // as well with detection deleted entirely — 13C is a position only a real overwrite disturbs.
    fireEvent.click(screen.getByRole("button", { name: "13C" }))
    expect(selectedNucleus()).toBe("13C")

    // The ordinary Bruker layout: expno 1 proton, expno 2 carbon. There is no single correct
    // toggle position, and picking one would mislabel the other experiment in the queue.
    dropFolder("Sample", {
      "1": { fid: "binary", acqus: acqus("1H") },
      "2": { fid: "binary", acqus: acqus("13C") },
    })

    await waitFor(() => expect(readout()).toBeInTheDocument())
    expect(readout()).toHaveTextContent(/holds 1H and 13C experiments/i)
    expect(readout()).toHaveTextContent(/nucleus recorded in its own file/i)
    expect(selectedNucleus()).toBe("13C")
  })

  it("names the solvent disagreement without silently swapping it", async () => {
    // Solvent is the field where the FORM wins over the file. A UI that quietly adopted the
    // instrument's value would contradict what actually runs.
    renderSection("DMSO-d6")
    dropFolder("Sample", { "1": { fid: "binary", acqus: acqus("1H", "CDCl3") } })

    await waitFor(() => expect(readout()).toBeInTheDocument())
    expect(readout()).toHaveTextContent(/instrument recorded CDCl3/i)
    expect(readout()).toHaveTextContent(/set to DMSO-d6, and that is what the analysis will use/i)
    // The read-only session solvent is untouched.
    expect(screen.getByLabelText(/Solvent/i)).toHaveValue("DMSO-d6")
  })

  it("says the file's solvent will be used when the session has none", async () => {
    renderSection("")
    dropFolder("Sample", { "1": { fid: "binary", acqus: acqus("1H", "Acetone") } })

    await waitFor(() => expect(readout()).toBeInTheDocument())
    expect(readout()).toHaveTextContent(/will use the Acetone recorded in the file/i)
  })

  it("warns when a forced vendor contradicts the files", async () => {
    renderSection()
    fireEvent.click(screen.getByRole("button", { name: /^Bruker$/i }))
    dropFolder("Sample", { "1": { fid: "binary", procpar: procpar("H1") } })

    await waitFor(() => expect(readout()).toBeInTheDocument())
    expect(readout()).toHaveTextContent(/Vendor is set to Bruker, but these files are Varian/i)
  })

  it("takes a folder and a loose archive dropped together", async () => {
    // The copy invites dropping both. Reading only the folder used to discard the archive.
    renderSection()
    dropFolder(
      "Sample",
      { "1": { fid: "binary", acqus: acqus("1H") } },
      [new File(["zip"], "extra.zip", { type: "application/zip" })],
    )

    await waitFor(() => {
      expect(screen.getByText("Sample/1")).toBeInTheDocument()
      expect(screen.getByText("extra.zip")).toBeInTheDocument()
    })
    // `dataTransfer.files` also lists the dropped DIRECTORY itself. Admitting it verbatim adds a
    // row for a folder that is not an archive, which then reports itself as unusable.
    expect(screen.queryByText("Sample", { exact: true })).not.toBeInTheDocument()
  })

  it("drains a directory reader that returns entries in batches", async () => {
    // Six files in one directory, delivered two at a time by the stub. A reader that calls
    // readEntries once sees only the first two — here, `fid` and `acqus` would be missed entirely
    // and the folder would be reported as holding no dataset at all.
    renderSection()
    dropFolder("Sample", {
      "1": {
        audita: "x",
        format: "x",
        pulseprogram: "x",
        uxnmr: "x",
        fid: "binary",
        acqus: acqus("1H"),
      },
    })

    await waitFor(() => expect(screen.getByText("Sample/1")).toBeInTheDocument())
    expect(readout()).toHaveTextContent("1H")
  })

  it("reports a folder with no readable dataset instead of failing quietly", async () => {
    renderSection()
    dropFolder("Notes", { "readme.txt": "no data here" })

    await waitFor(() =>
      expect(screen.getByText(/No Bruker or Varian\/Agilent dataset found/i)).toBeInTheDocument(),
    )
    // Nothing was read, so the readout must not appear claiming an empty result.
    expect(readout()).not.toBeInTheDocument()
  })

  it("skips a 2D experiment and leaves the 1D one queued", async () => {
    renderSection()
    dropFolder("Sample", {
      "1": { fid: "binary", acqus: acqus("1H") },
      "2": { ser: "binary", acqus: acqus("1H") },
    })

    await waitFor(() => expect(screen.getByText("Sample/1")).toBeInTheDocument())
    // A 2D dataset has `ser` rather than `fid` and this reader is 1D. Dropping it and saying
    // nothing would read as "all your experiments are here".
    expect(screen.queryByText("Sample/2")).not.toBeInTheDocument()
  })
})

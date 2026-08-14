import { describe, expect, it } from "vitest"
import { unzipSync } from "fflate"
import {
  archiveNameForEntries,
  detectVendorDataset,
  experimentArchiveName,
  formatBytes,
  splitVendorFolderByExperiment,
  vendorFolderEntriesFromFileList,
  zipVendorFolder,
  type VendorFolderEntry,
} from "@/src/lib/spectracheck/vendor-folder-drop"

function entry(path: string, bytes = 8): VendorFolderEntry {
  return { path, file: new File([new Uint8Array(bytes)], path.split("/").pop() ?? path) }
}

/** Layout of a real Bruker acquisition folder. The folder name is a neutral
 * stand-in: real sample names are not published, and nothing here depends on it. */
const BRUKER = [
  "Sample/34/fid",
  "Sample/34/acqus",
  "Sample/34/acqu",
  "Sample/34/pulseprogram.precomp",
  "Sample/34/pdata/1/procs",
]

describe("vendor dataset detection", () => {
  it("recognises a Bruker folder by fid + acqus in the same directory", () => {
    const d = detectVendorDataset(BRUKER.map((p) => entry(p)))
    expect(d.usable).toBe(true)
    expect(d.kind).toBe("bruker")
    expect(d.experiments).toHaveLength(1)
    expect(d.experiments[0].dir).toBe("Sample/34")
    expect(d.reason).toBeNull()
  })

  it("recognises a Varian/Agilent folder by fid + procpar", () => {
    const d = detectVendorDataset([entry("run/fid"), entry("run/procpar"), entry("run/text")])
    expect(d.usable).toBe(true)
    expect(d.kind).toBe("varian")
  })

  it("finds every experiment when a whole sample folder is dropped", () => {
    const d = detectVendorDataset(
      ["Raw/33/fid", "Raw/33/acqus", "Raw/34/fid", "Raw/34/acqus"].map((p) => entry(p)),
    )
    expect(d.experiments.map((e) => e.dir)).toEqual(["Raw/33", "Raw/34"])
    expect(d.kind).toBe("bruker")
  })

  it("refuses a folder with no dataset, and says why in plain language", () => {
    const d = detectVendorDataset([entry("notes/readme.txt"), entry("notes/plot.png")])
    expect(d.usable).toBe(false)
    expect(d.reason).toContain("fid")
    // no endpoint paths / status codes / field names in user-facing copy
    expect(d.reason).not.toMatch(/POST |http|_json|\b4\d\d\b/)
  })

  it("does not treat a lone fid (no acqus/procpar) as processable", () => {
    const d = detectVendorDataset([entry("x/fid")])
    expect(d.usable).toBe(false)
  })

  it("ignores OS junk so it neither counts nor reaches the archive", () => {
    const d = detectVendorDataset([
      entry("Sample/34/fid"),
      entry("Sample/34/acqus"),
      entry("Sample/.DS_Store"),
      entry("Sample/._fid"),
      entry("__MACOSX/Sample/34/fid"),
    ])
    expect(d.usable).toBe(true)
    expect(d.fileCount).toBe(2)
  })

  it("reports an empty folder rather than pretending it is a dataset", () => {
    const d = detectVendorDataset([])
    expect(d.usable).toBe(false)
    expect(d.reason).toContain("empty")
  })
})

describe("archive naming", () => {
  it("names the archive after the dropped root folder", () => {
    expect(archiveNameForEntries(BRUKER.map((p) => entry(p)))).toBe("Sample.zip")
  })

  it("sanitises spaces and punctuation out of the name", () => {
    expect(archiveNameForEntries([entry("My Sample #1/fid")])).toBe("My_Sample_1.zip")
  })
})

describe("client-side zipping", () => {
  it("produces a zip that PRESERVES relative paths (the backend groups members per directory)", async () => {
    const file = await zipVendorFolder(BRUKER.map((p) => entry(p)))
    expect(file.name).toBe("Sample.zip")
    expect(file.type).toBe("application/zip")

    const bytes = new Uint8Array(await file.arrayBuffer())
    const members = Object.keys(unzipSync(bytes)).sort()
    // Paths must survive intact — a flattened archive would break dataset detection.
    expect(members).toContain("Sample/34/fid")
    expect(members).toContain("Sample/34/acqus")
    expect(members).toContain("Sample/34/pdata/1/procs")
  })

  it("omits OS junk from the archive", async () => {
    const file = await zipVendorFolder([
      entry("Sample/34/fid"),
      entry("Sample/34/acqus"),
      entry("Sample/.DS_Store"),
      entry("__MACOSX/Sample/34/fid"),
    ])
    const members = Object.keys(unzipSync(new Uint8Array(await file.arrayBuffer())))
    expect(members.sort()).toEqual(["Sample/34/acqus", "Sample/34/fid"])
  })

  it("reports progress and refuses a folder with nothing usable", async () => {
    const seen: number[] = []
    await zipVendorFolder(BRUKER.map((p) => entry(p)), { onProgress: (d) => seen.push(d) })
    expect(seen).toEqual([1, 2, 3, 4, 5])
    await expect(zipVendorFolder([entry("Sample/.DS_Store")])).rejects.toThrow(/no usable files/i)
  })
})

describe("splitting a dropped folder into one archive per experiment", () => {
  it("gives every experiment its own bundle instead of merging them into one", () => {
    const bundles = splitVendorFolderByExperiment(
      ["Raw/33/fid", "Raw/33/acqus", "Raw/34/fid", "Raw/34/acqus"].map((p) => entry(p)),
    )
    expect(bundles.map((b) => b.dir)).toEqual(["Raw/33", "Raw/34"])
    expect(bundles.map((b) => b.archiveName)).toEqual(["Raw_33.zip", "Raw_34.zip"])
    expect(bundles.every((b) => b.fileCount === 2)).toBe(true)
  })

  it("keeps a Bruker experiment's nested pdata files with their experiment", () => {
    const [bundle] = splitVendorFolderByExperiment(BRUKER.map((p) => entry(p)))
    expect(bundle.entries.map((e) => e.path)).toContain("Sample/34/pdata/1/procs")
    expect(bundle.fileCount).toBe(5)
  })

  it("does not let a sibling with a shorter number steal the deeper one's files", () => {
    const bundles = splitVendorFolderByExperiment(
      ["Raw/3/fid", "Raw/3/acqus", "Raw/34/fid", "Raw/34/acqus"].map((p) => entry(p)),
    )
    const three = bundles.find((b) => b.dir === "Raw/3")
    expect(three?.entries.map((e) => e.path).sort()).toEqual(["Raw/3/acqus", "Raw/3/fid"])
  })

  it("gives a nested dataset to the deepest experiment that contains it, not its parent", () => {
    const bundles = splitVendorFolderByExperiment(
      ["run/fid", "run/acqus", "run/inner/fid", "run/inner/acqus"].map((p) => entry(p)),
    )
    const outer = bundles.find((b) => b.dir === "run")
    const inner = bundles.find((b) => b.dir === "run/inner")
    expect(outer?.entries.map((e) => e.path).sort()).toEqual(["run/acqus", "run/fid"])
    expect(inner?.entries.map((e) => e.path).sort()).toEqual(["run/inner/acqus", "run/inner/fid"])
  })

  it("handles a dataset sitting at the dropped root, where the directory is empty", () => {
    const bundles = splitVendorFolderByExperiment([entry("fid"), entry("acqus"), entry("pdata/1/procs")])
    expect(bundles).toHaveLength(1)
    expect(bundles[0].dir).toBe("")
    expect(bundles[0].entries.map((e) => e.path).sort()).toEqual(["acqus", "fid", "pdata/1/procs"])
    expect(bundles[0].archiveName).toBe("raw_fid_experiment.zip")
  })

  it("keeps OS junk out of the bundles and out of their counts", () => {
    const [bundle] = splitVendorFolderByExperiment([
      entry("Sample/34/fid"),
      entry("Sample/34/acqus"),
      entry("Sample/34/.DS_Store"),
      entry("__MACOSX/Sample/34/fid"),
    ])
    expect(bundle.entries.map((e) => e.path).sort()).toEqual(["Sample/34/acqus", "Sample/34/fid"])
    expect(bundle.fileCount).toBe(2)
  })

  it("leaves files that belong to no experiment out of every bundle", () => {
    const bundles = splitVendorFolderByExperiment(
      ["Raw/34/fid", "Raw/34/acqus", "Raw/notes.txt"].map((p) => entry(p)),
    )
    expect(bundles).toHaveLength(1)
    expect(bundles[0].entries.map((e) => e.path)).not.toContain("Raw/notes.txt")
  })

  it("reports the uncompressed size the server will measure", () => {
    const bundles = splitVendorFolderByExperiment([
      entry("Raw/34/fid", 1000),
      entry("Raw/34/acqus", 24),
    ])
    expect(bundles[0].totalBytes).toBe(1024)
  })

  it("returns nothing when the folder holds no dataset at all", () => {
    expect(splitVendorFolderByExperiment([entry("notes/readme.txt")])).toEqual([])
  })

  it("names archives from the full path so two roots sharing an expno stay distinct", () => {
    const bundles = splitVendorFolderByExperiment(
      ["A/1/fid", "A/1/acqus", "B/1/fid", "B/1/acqus"].map((p) => entry(p)),
    )
    expect(bundles.map((b) => b.archiveName)).toEqual(["A_1.zip", "B_1.zip"])
  })

  it("still separates two experiments whose names sanitise to the same string", () => {
    const bundles = splitVendorFolderByExperiment(
      ["My 1/fid", "My 1/acqus", "My#1/fid", "My#1/acqus"].map((p) => entry(p)),
    )
    expect(new Set(bundles.map((b) => b.archiveName)).size).toBe(2)
    expect(bundles.map((b) => b.archiveName)).toContain("My_1-2.zip")
  })

  it("zips one bundle at a time into an archive the server can still read", async () => {
    const [bundle] = splitVendorFolderByExperiment(BRUKER.map((p) => entry(p)))
    const file = await zipVendorFolder(bundle.entries, { name: bundle.archiveName })
    expect(file.name).toBe("Sample_34.zip")
    const members = Object.keys(unzipSync(new Uint8Array(await file.arrayBuffer()))).sort()
    expect(members).toEqual(["Sample/34/acqu", "Sample/34/acqus", "Sample/34/fid", "Sample/34/pdata/1/procs", "Sample/34/pulseprogram.precomp"])
  })
})

describe("per-experiment archive naming", () => {
  it("flattens the directory path so the name says which experiment it is", () => {
    expect(experimentArchiveName("Sample/Raw/34")).toBe("Sample_Raw_34.zip")
  })

  it("keeps a Varian .fid directory suffix readable", () => {
    expect(experimentArchiveName("proton01.fid")).toBe("proton01.fid.zip")
  })

  it("never emits a path traversal or a bare extension", () => {
    expect(experimentArchiveName("../../etc")).toBe("etc.zip")
    expect(experimentArchiveName("...")).toBe("raw_fid_experiment.zip")
  })

  it("clamps an very deep path but keeps the specific tail", () => {
    const name = experimentArchiveName(`${"a/".repeat(200)}34`)
    expect(name.length).toBeLessThanOrEqual(124)
    expect(name.endsWith("_34.zip")).toBe(true)
  })
})

describe("folder picker input", () => {
  it("uses webkitRelativePath so a picked folder keeps its structure", () => {
    const f = new File([new Uint8Array(4)], "fid")
    Object.defineProperty(f, "webkitRelativePath", { value: "Sample/34/fid" })
    expect(vendorFolderEntriesFromFileList([f])[0].path).toBe("Sample/34/fid")
  })

  it("falls back to the bare name when the browser omits a relative path", () => {
    expect(vendorFolderEntriesFromFileList([new File([], "fid")])[0].path).toBe("fid")
  })
})

describe("formatBytes", () => {
  it("renders human sizes for the drop summary", () => {
    expect(formatBytes(0)).toBe("0 B")
    expect(formatBytes(900)).toBe("900 B")
    expect(formatBytes(1536)).toBe("1.5 KB")
    expect(formatBytes(4.6 * 1024 * 1024)).toBe("4.6 MB")
  })
})

describe("experiment ordering", () => {
  it("queues Bruker expnos in numeric order, not lexicographic", () => {
    // A chemist numbers expnos as numbers. Sorted as strings, experiment 10 lands above
    // experiment 2 and a straightforward series comes back looking shuffled.
    const entries = ["1", "2", "10", "11", "3"].flatMap((expno) => [
      entry(`Sample/${expno}/fid`),
      entry(`Sample/${expno}/acqus`),
    ])

    const bundles = splitVendorFolderByExperiment(entries)

    expect(bundles.map((b) => b.dir)).toEqual([
      "Sample/1",
      "Sample/2",
      "Sample/3",
      "Sample/10",
      "Sample/11",
    ])
  })

  it("orders zero-padded and mixed-width names the way a reader expects", () => {
    const entries = ["A/007", "A/8", "A/70"].flatMap((dir) => [
      entry(`${dir}/fid`),
      entry(`${dir}/procpar`),
    ])

    expect(splitVendorFolderByExperiment(entries).map((b) => b.dir)).toEqual([
      "A/007",
      "A/8",
      "A/70",
    ])
  })
})

describe("experiments the 1D reader cannot use", () => {
  it("reports a 2D experiment as skipped instead of dropping it in silence", () => {
    // A Bruker 2D holds `ser`, not `fid`, so it can never be a 1D dataset. Saying nothing left
    // the panel claiming every experiment in the folder had been queued.
    const entries = [
      entry("Sample/1/fid"),
      entry("Sample/1/acqus"),
      entry("Sample/2/fid"),
      entry("Sample/2/acqus"),
      entry("Sample/4/ser"),
      entry("Sample/4/acqus"),
    ]

    const detection = detectVendorDataset(entries)

    expect(detection.experiments.map((e) => e.dir)).toEqual(["Sample/1", "Sample/2"])
    expect(detection.skippedDirs).toEqual(["Sample/4"])
  })

  it("does not list ordinary sub-folders as skipped experiments", () => {
    // pdata/1 fails the same test but was never an experiment; listing it would bury a real one.
    const detection = detectVendorDataset([
      entry("Sample/1/fid"),
      entry("Sample/1/acqus"),
      entry("Sample/1/pdata/1/procs"),
    ])

    expect(detection.skippedDirs).toEqual([])
  })
})

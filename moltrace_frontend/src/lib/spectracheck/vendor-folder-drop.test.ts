import { describe, expect, it } from "vitest"
import { unzipSync } from "fflate"
import {
  archiveNameForEntries,
  detectVendorDataset,
  formatBytes,
  vendorFolderEntriesFromFileList,
  zipVendorFolder,
  type VendorFolderEntry,
} from "@/src/lib/spectracheck/vendor-folder-drop"

function entry(path: string, bytes = 8): VendorFolderEntry {
  return { path, file: new File([new Uint8Array(bytes)], path.split("/").pop() ?? path) }
}

/** Layout of a real Bruker acquisition folder (mirrors the 1-Napamine test data). */
const BRUKER = [
  "Nap/34/fid",
  "Nap/34/acqus",
  "Nap/34/acqu",
  "Nap/34/pulseprogram.precomp",
  "Nap/34/pdata/1/procs",
]

describe("vendor dataset detection", () => {
  it("recognises a Bruker folder by fid + acqus in the same directory", () => {
    const d = detectVendorDataset(BRUKER.map((p) => entry(p)))
    expect(d.usable).toBe(true)
    expect(d.kind).toBe("bruker")
    expect(d.experiments).toHaveLength(1)
    expect(d.experiments[0].dir).toBe("Nap/34")
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
      entry("Nap/34/fid"),
      entry("Nap/34/acqus"),
      entry("Nap/.DS_Store"),
      entry("Nap/._fid"),
      entry("__MACOSX/Nap/34/fid"),
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
    expect(archiveNameForEntries(BRUKER.map((p) => entry(p)))).toBe("Nap.zip")
  })

  it("sanitises spaces and punctuation out of the name", () => {
    expect(archiveNameForEntries([entry("My Sample #1/fid")])).toBe("My_Sample_1.zip")
  })
})

describe("client-side zipping", () => {
  it("produces a zip that PRESERVES relative paths (the backend groups members per directory)", async () => {
    const file = await zipVendorFolder(BRUKER.map((p) => entry(p)))
    expect(file.name).toBe("Nap.zip")
    expect(file.type).toBe("application/zip")

    const bytes = new Uint8Array(await file.arrayBuffer())
    const members = Object.keys(unzipSync(bytes)).sort()
    // Paths must survive intact — a flattened archive would break dataset detection.
    expect(members).toContain("Nap/34/fid")
    expect(members).toContain("Nap/34/acqus")
    expect(members).toContain("Nap/34/pdata/1/procs")
  })

  it("omits OS junk from the archive", async () => {
    const file = await zipVendorFolder([
      entry("Nap/34/fid"),
      entry("Nap/34/acqus"),
      entry("Nap/.DS_Store"),
      entry("__MACOSX/Nap/34/fid"),
    ])
    const members = Object.keys(unzipSync(new Uint8Array(await file.arrayBuffer())))
    expect(members.sort()).toEqual(["Nap/34/acqus", "Nap/34/fid"])
  })

  it("reports progress and refuses a folder with nothing usable", async () => {
    const seen: number[] = []
    await zipVendorFolder(BRUKER.map((p) => entry(p)), { onProgress: (d) => seen.push(d) })
    expect(seen).toEqual([1, 2, 3, 4, 5])
    await expect(zipVendorFolder([entry("Nap/.DS_Store")])).rejects.toThrow(/no usable files/i)
  })
})

describe("folder picker input", () => {
  it("uses webkitRelativePath so a picked folder keeps its structure", () => {
    const f = new File([new Uint8Array(4)], "fid")
    Object.defineProperty(f, "webkitRelativePath", { value: "Nap/34/fid" })
    expect(vendorFolderEntriesFromFileList([f])[0].path).toBe("Nap/34/fid")
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

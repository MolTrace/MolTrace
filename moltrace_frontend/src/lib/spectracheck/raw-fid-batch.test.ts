import { beforeEach, describe, expect, it } from "vitest"
import {
  RAW_FID_MAX_ARCHIVE_FILES,
  classifyRawFidBatchFailure,
  createBlockedRawFidBatchItem,
  createRawFidBatchItem,
  estimateRemainingMs,
  formatBatchBytes,
  formatBatchDuration,
  isRawFidBatchItemRunnable,
  preflightRawFidArchive,
  readRawFidBatchItemFacts,
  resetRawFidBatchItemIds,
  summarizeRawFidBatch,
  type RawFidBatchItem,
} from "@/src/lib/spectracheck/raw-fid-batch"

function archive(name: string, size = 2048): File {
  return new File([new Uint8Array(Math.min(size, 64))], name)
}

function item(patch: Partial<RawFidBatchItem>): RawFidBatchItem {
  return { ...createRawFidBatchItem({ file: archive("a.zip") }), ...patch }
}

beforeEach(() => {
  resetRawFidBatchItemIds()
})

describe("admitting an archive to the queue", () => {
  it("accepts the three archive formats the analyzer reads", () => {
    for (const name of ["a.zip", "b.tar.gz", "c.tgz", "D.ZIP"]) {
      expect(preflightRawFidArchive({ name, size: 10 }).ok).toBe(true)
    }
  })

  it("refuses a file that is not an archive, and names the formats that work", () => {
    const result = preflightRawFidArchive({ name: "spectrum.csv", size: 10 })
    expect(result.ok).toBe(false)
    expect(result).toMatchObject({ reason: expect.stringContaining(".tar.gz") })
  })

  it("refuses an oversize dataset before spending the upload, and says the measured size", () => {
    const result = preflightRawFidArchive({
      name: "big.zip",
      size: 10,
      uncompressedBytes: 400 * 1024 * 1024,
    })
    expect(result.ok).toBe(false)
    expect(result).toMatchObject({ reason: expect.stringContaining("400 MB") })
  })

  it("refuses a dataset with too many files", () => {
    const result = preflightRawFidArchive({
      name: "many.zip",
      size: 10,
      fileCount: RAW_FID_MAX_ARCHIVE_FILES + 1,
    })
    expect(result.ok).toBe(false)
    expect(result).toMatchObject({ reason: expect.stringContaining("files") })
  })

  it("refuses an empty archive", () => {
    expect(preflightRawFidArchive({ name: "e.zip", size: 0 }).ok).toBe(false)
  })

  it("never leaks implementation language into a refusal a chemist reads", () => {
    const reasons = [
      preflightRawFidArchive({ name: "x.csv", size: 1 }),
      preflightRawFidArchive({ name: "x.zip", size: 0 }),
      preflightRawFidArchive({ name: "x.zip", size: 1, uncompressedBytes: 9e9 }),
      preflightRawFidArchive({ name: "x.zip", size: 1, fileCount: 99999 }),
    ]
      .map((r) => (r.ok ? "" : r.reason))
      .join(" ")
    expect(reasons).not.toMatch(/POST|http|backend|_json|\b4\d\d\b|payload|endpoint/i)
  })
})

describe("queue items", () => {
  it("gives each item a distinct id even when two datasets share a filename", () => {
    const a = createRawFidBatchItem({ file: archive("fid.zip") })
    const b = createRawFidBatchItem({ file: archive("fid.zip") })
    expect(a.id).not.toBe(b.id)
  })

  it("labels an item by its experiment folder when one was split out", () => {
    const created = createRawFidBatchItem({
      file: archive("Raw_34.zip"),
      label: "Raw/34",
      sourceDir: "Raw/34",
    })
    expect(created.label).toBe("Raw/34")
    expect(created.status).toBe("queued")
  })

  it("falls back to the filename when there is no folder to name it after", () => {
    expect(createRawFidBatchItem({ file: archive("sample.zip") }).label).toBe("sample.zip")
  })

  it("admits a refused archive as a blocked row rather than dropping it silently", () => {
    const created = createRawFidBatchItem({ file: archive("notes.txt") })
    expect(created.status).toBe("blocked")
    expect(created.error).toBeTruthy()
  })

  it("treats every not-yet-succeeded state as re-runnable, and a finished one as not", () => {
    expect(isRawFidBatchItemRunnable(item({ status: "queued" }))).toBe(true)
    expect(isRawFidBatchItemRunnable(item({ status: "failed" }))).toBe(true)
    expect(isRawFidBatchItemRunnable(item({ status: "cancelled" }))).toBe(true)
    expect(isRawFidBatchItemRunnable(item({ status: "unconfirmed" }))).toBe(true)
    expect(isRawFidBatchItemRunnable(item({ status: "done" }))).toBe(false)
    expect(isRawFidBatchItemRunnable(item({ status: "running" }))).toBe(false)
    // A locally refused archive is not re-runnable: nothing about re-sending it would change.
    expect(isRawFidBatchItemRunnable(item({ status: "blocked" }))).toBe(false)
  })

  it("counts the queue by state", () => {
    const counts = summarizeRawFidBatch([
      item({ status: "done" }),
      item({ status: "done" }),
      item({ status: "failed" }),
      item({ status: "running" }),
      item({ status: "blocked" }),
    ])
    expect(counts).toMatchObject({ total: 5, done: 2, failed: 1, running: 1, blocked: 1, runnable: 1 })
  })
})

describe("classifying a failed dataset", () => {
  class FakeApiError extends Error {
    constructor(public status: number) {
      super("boom")
    }
  }

  it("treats a stop as a stop, not a failure", () => {
    const abort = new DOMException("aborted", "AbortError")
    expect(classifyRawFidBatchFailure(abort, "ignored")).toMatchObject({
      status: "cancelled",
      stopsRun: false,
    })
  })

  it("does NOT call a timed-out dataset failed, because it was probably still running", () => {
    const verdict = classifyRawFidBatchFailure(new FakeApiError(504), "Could not reach the service.")
    expect(verdict.status).toBe("unconfirmed")
    expect(verdict.stopsRun).toBe(false)
    expect(verdict.message).toMatch(/still being analyzed/i)
    expect(verdict.message).toMatch(/run is kept/i)
  })

  it("stops the whole run on a refusal that would repeat for every dataset", () => {
    expect(classifyRawFidBatchFailure(new FakeApiError(403), "No access.").stopsRun).toBe(true)
    expect(classifyRawFidBatchFailure(new FakeApiError(401), "Sign in.").stopsRun).toBe(true)
    expect(classifyRawFidBatchFailure(new FakeApiError(404), "Not available.").stopsRun).toBe(true)
    expect(classifyRawFidBatchFailure(new FakeApiError(429), "Slow down.").stopsRun).toBe(true)
  })

  it("lets the run continue past a failure that is about one dataset", () => {
    const verdict = classifyRawFidBatchFailure(new FakeApiError(400), "That archive could not be read.")
    expect(verdict).toMatchObject({ status: "failed", stopsRun: false })
    expect(verdict.message).toBe("That archive could not be read.")
  })

  it("passes the caller's already-safe message through untouched", () => {
    expect(classifyRawFidBatchFailure(new Error("x"), "Readable text.").message).toBe("Readable text.")
  })

  it("keeps implementation language out of the messages it writes itself", () => {
    const own = [
      classifyRawFidBatchFailure(new DOMException("a", "AbortError"), ""),
      classifyRawFidBatchFailure(new FakeApiError(504), ""),
      classifyRawFidBatchFailure(new FakeApiError(429), ""),
    ]
      .map((v) => v.message)
      .join(" ")
    expect(own).not.toMatch(/POST|http|backend|_json|\b4\d\d\b|abort|endpoint/i)
  })
})

describe("a dataset refused before it was ever packaged", () => {
  it("becomes a blocked row that explains itself", () => {
    const blocked = createBlockedRawFidBatchItem({
      label: "Raw/34",
      reason: "Dataset expands to 400 MB; the limit is 250 MB once unpacked.",
      uncompressedBytes: 400 * 1024 * 1024,
    })
    expect(blocked.status).toBe("blocked")
    expect(blocked.error).toMatch(/400 MB/)
    expect(isRawFidBatchItemRunnable(blocked)).toBe(false)
  })
})

describe("reading one analysis into a queue row", () => {
  it("reports the vendor the analyzer recognised", () => {
    const facts = readRawFidBatchItemFacts({ vendor_detected: "bruker", nucleus: "13C" })
    expect(facts.vendorDetected).toBe("bruker")
    expect(facts.nucleus).toBe("13C")
  })

  it("counts peaks and reads the point count and field", () => {
    const facts = readRawFidBatchItemFacts({
      peaks: [{ ppm: 1 }, { ppm: 2 }, { ppm: 3 }],
      point_count: 65536,
      field_mhz: 400.13,
    })
    expect(facts.peakCount).toBe(3)
    expect(facts.pointCount).toBe(65536)
    expect(facts.fieldMhz).toBeCloseTo(400.13)
  })

  it("finds which experiment folder was analyzed wherever the response reports it", () => {
    expect(readRawFidBatchItemFacts({ file_inventory: { dataset_root: "Nap/34" } }).datasetRoot).toBe("Nap/34")
    expect(readRawFidBatchItemFacts({ metadata: { file_inventory: { dataset_root: "Nap/35" } } }).datasetRoot).toBe("Nap/35")
  })

  it("returns nulls rather than invented defaults for a response that omits everything", () => {
    const facts = readRawFidBatchItemFacts({})
    expect(facts).toMatchObject({
      vendorDetected: null,
      nucleus: null,
      datasetRoot: null,
      pointCount: null,
      peakCount: null,
      fieldMhz: null,
      sha256: null,
      warnings: [],
    })
  })

  it("survives a response that is not an object at all", () => {
    expect(readRawFidBatchItemFacts(null).warnings).toEqual([])
    expect(readRawFidBatchItemFacts("nope").peakCount).toBeNull()
  })

  it("normalises a single warning string into a list", () => {
    expect(readRawFidBatchItemFacts({ warnings: "one thing" }).warnings).toEqual(["one thing"])
  })

  it("rejects a zero or negative point count instead of showing it", () => {
    expect(readRawFidBatchItemFacts({ point_count: 0 }).pointCount).toBeNull()
    expect(readRawFidBatchItemFacts({ field_mhz: -1 }).fieldMhz).toBeNull()
  })
})

describe("queue formatting and estimates", () => {
  it("formats sizes and durations for a dense row", () => {
    expect(formatBatchBytes(1536)).toBe("1.5 KB")
    expect(formatBatchDuration(4200)).toBe("4s")
    expect(formatBatchDuration(95_000)).toBe("1m 35s")
    expect(formatBatchDuration(null)).toBe("—")
  })

  it("gives no estimate until something has actually finished", () => {
    expect(estimateRemainingMs([item({ status: "queued" }), item({ status: "running" })])).toBeNull()
  })

  it("estimates the rest of the run from the median finished item, not the worst one", () => {
    const estimate = estimateRemainingMs([
      item({ status: "done", durationMs: 10_000 }),
      item({ status: "done", durationMs: 12_000 }),
      item({ status: "done", durationMs: 200_000 }),
      item({ status: "queued" }),
      item({ status: "queued" }),
    ])
    expect(estimate).toBe(24_000)
  })

  it("stops estimating once nothing is left to run", () => {
    expect(estimateRemainingMs([item({ status: "done", durationMs: 5_000 })])).toBeNull()
  })
})

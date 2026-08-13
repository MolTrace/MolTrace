/**
 * Multi-dataset raw-FID queue — the model behind processing a whole folder of experiments in one
 * pass, the way an instrument-room chemist works in MestReNova.
 *
 * Everything here is pure: types, admission rules, per-item pre-flight, and the readers that turn
 * one analysis response into the few numbers a queue row shows. The runner and the UI live
 * elsewhere so this file stays testable without a DOM.
 *
 * Two facts shape the whole design and are not negotiable:
 *
 *  1. There is no multi-file analysis route — the queue is a client-side fan-out, one request per
 *     archive.
 *  2. Those requests must run ONE AT A TIME. The analysis work happens inline on the server's
 *     request loop, so several at once do not overlap; they queue anyway and block unrelated work
 *     while they do. Running them in sequence is not a limitation we accept, it is the only shape
 *     that is actually faster.
 */

/**
 * The analyzer's own limits, copied so a refusal can be explained here instead of after a
 * multi-megabyte upload. Each is the DEFAULT the service ships with — re-verify against the named
 * constant rather than adjusting these by feel, and keep the comparison non-strict-free (`>`, not
 * `>=`) so a dataset sitting exactly on a limit is admitted here exactly as it is there.
 *
 * The archive-size ceiling is operator-configurable (`RAW_ARCHIVE_MAX_BYTES`); the other two are
 * fixed in code. A deployment that raises it makes this check the stricter of the two, which is
 * why the message names the measurement rather than claiming the file is invalid.
 */
/** `raw_archive_max_bytes` — nmrcheck/settings.py, DEFAULT_RAW_ARCHIVE_MAX_BYTES in raw_vault.py. */
export const RAW_FID_MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
/** `_MAX_ARCHIVE_UNCOMPRESSED_BYTES` — nmrcheck/fid.py. Measured while the archive is expanded. */
export const RAW_FID_MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
/** `_MAX_ARCHIVE_FILES` — nmrcheck/fid.py. Most members one archive may contain. */
export const RAW_FID_MAX_ARCHIVE_FILES = 5000
/**
 * Queue ceiling. Each finished dataset keeps its full analysis in memory so the reviewer can flip
 * back to any of them instantly; past this many the tab is holding more than it should.
 */
export const RAW_FID_BATCH_MAX_ITEMS = 64

export type RawFidBatchMode = "scan" | "process"

export type RawFidBatchStatus =
  /** Admitted, waiting its turn. */
  | "queued"
  /** In flight right now. */
  | "running"
  /** Finished with a usable result. */
  | "done"
  /** The analysis was attempted and did not succeed. */
  | "failed"
  /** The user stopped it, or stopped the run while it was waiting. */
  | "cancelled"
  /** Refused before any upload, by a rule we can check locally. */
  | "blocked"
  /**
   * The wait for a result ran out. Distinct from `failed` on purpose: the analysis was very
   * likely still running, and its record is kept regardless — so calling it a failure would be
   * a lie the reviewer might act on.
   */
  | "unconfirmed"

export type RawFidBatchItem = {
  /** Stable for the item's whole life — React keys, dev snapshots, and selection all use it. */
  id: string
  file: File
  /** What the chemist calls this dataset: the experiment folder when we split one, else the name. */
  label: string
  /** Experiment directory this came from, when it was split out of a dropped folder. */
  sourceDir: string | null
  /** Files inside the archive, when we packaged it and therefore know. */
  fileCount: number | null
  /** Uncompressed bytes, when known — this is the figure the size limit is measured against. */
  uncompressedBytes: number | null
  status: RawFidBatchStatus
  /** Which analysis produced `result`. Null until it has run. */
  mode: RawFidBatchMode | null
  /** Display-ready failure text. Never a raw error. */
  error: string | null
  startedAt: number | null
  durationMs: number | null
  result: unknown
}

export type RawFidBatchCounts = {
  total: number
  queued: number
  running: number
  done: number
  failed: number
  cancelled: number
  blocked: number
  unconfirmed: number
  /** Items that could still be run — queued, plus anything that stopped short of a result. */
  runnable: number
}

/**
 * The single in-flight queue run.
 *
 * Module scope, not component state, for two reasons: the section unmounts on every tab switch
 * while a run is minutes of work, and two runs must never work the same queue at once.
 *
 * `generation` is what makes that safe across teardown. A run claims a generation when it starts
 * and only clears the flags if it still holds it, so a loop that was abandoned — the workspace
 * unmounted while it was mid-request — cannot reach in later and clear the claim of a run started
 * after it. It also gives the abandoned loop a cheap way to notice it is no longer wanted and
 * stop, instead of quietly working through another nineteen datasets nobody is watching.
 */
export type RawFidBatchRunHandle = {
  active: boolean
  stop: boolean
  controller: AbortController | null
  generation: number
}

export const rawFidBatchRun: RawFidBatchRunHandle = {
  active: false,
  stop: false,
  controller: null,
  generation: 0,
}

/** Claim the run. Returns the generation to pass back to `endRawFidBatchRun`, or null if busy. */
export function beginRawFidBatchRun(): number | null {
  if (rawFidBatchRun.active) return null
  rawFidBatchRun.generation += 1
  rawFidBatchRun.active = true
  rawFidBatchRun.stop = false
  rawFidBatchRun.controller = null
  return rawFidBatchRun.generation
}

/** Release the run, but only if this generation still holds it. */
export function endRawFidBatchRun(generation: number): void {
  if (generation !== rawFidBatchRun.generation) return
  rawFidBatchRun.active = false
  rawFidBatchRun.stop = false
  rawFidBatchRun.controller = null
}

/** True while this generation is still the run everyone means. */
export function isRawFidBatchRunCurrent(generation: number): boolean {
  return generation === rawFidBatchRun.generation && !rawFidBatchRun.stop
}

/** Ask the current run to stop. The loop exits at its next check and releases its own claim. */
export function stopRawFidBatchRun(): void {
  rawFidBatchRun.stop = true
  rawFidBatchRun.controller?.abort()
}

/**
 * Tear the run down because the state it writes into is going away (the workspace unmounted, or
 * the session was reset). Unlike `stopRawFidBatchRun` this releases the claim immediately —
 * otherwise the next mount finds `active` still true and every Run button silently does nothing —
 * and bumps the generation so the abandoned loop's own cleanup cannot clear a newer run.
 */
export function abortRawFidBatchRun(): void {
  rawFidBatchRun.stop = true
  rawFidBatchRun.controller?.abort()
  rawFidBatchRun.generation += 1
  rawFidBatchRun.active = false
  rawFidBatchRun.controller = null
}

let batchItemSequence = 0

/** Stable, collision-free id. Not derived from the filename: two datasets can share one. */
export function nextRawFidBatchItemId(): string {
  batchItemSequence += 1
  return `rawfid-${batchItemSequence}`
}

/** Test-only: make ids predictable across cases. */
export function resetRawFidBatchItemIds(): void {
  batchItemSequence = 0
}

export type RawFidPreflight = { ok: true } | { ok: false; reason: string }

/**
 * Everything we can refuse without spending a multi-megabyte upload first.
 *
 * The limits mirror what the analyzer enforces while it expands the archive. Checking them here
 * turns a slow round trip that ends in a refusal into an instant, specific explanation — and each
 * message names the measurement that failed, because "invalid file" tells a chemist nothing.
 */
export function preflightRawFidArchive(candidate: {
  name: string
  size: number
  uncompressedBytes?: number | null
  fileCount?: number | null
}): RawFidPreflight {
  if (!/\.(zip|tar\.gz|tgz)$/i.test(candidate.name)) {
    return {
      ok: false,
      reason: "Not a recognised archive — a dataset arrives as .zip, .tar.gz or .tgz.",
    }
  }
  if (candidate.size <= 0) {
    return { ok: false, reason: "This archive is empty." }
  }
  if (candidate.size > RAW_FID_MAX_ARCHIVE_BYTES) {
    return {
      ok: false,
      reason: `Archive is ${formatBatchBytes(candidate.size)}; the limit is ${formatBatchBytes(RAW_FID_MAX_ARCHIVE_BYTES)}.`,
    }
  }
  const uncompressed = candidate.uncompressedBytes
  if (uncompressed != null && uncompressed > RAW_FID_MAX_UNCOMPRESSED_BYTES) {
    return {
      ok: false,
      reason: `Dataset expands to ${formatBatchBytes(uncompressed)}; the limit is ${formatBatchBytes(RAW_FID_MAX_UNCOMPRESSED_BYTES)} once unpacked.`,
    }
  }
  const fileCount = candidate.fileCount
  if (fileCount != null && fileCount > RAW_FID_MAX_ARCHIVE_FILES) {
    return {
      ok: false,
      reason: `Dataset holds ${fileCount.toLocaleString()} files; the limit is ${RAW_FID_MAX_ARCHIVE_FILES.toLocaleString()}.`,
    }
  }
  return { ok: true }
}

/** Build an item, pre-flighted, so a refusal is visible in the queue instead of thrown away. */
export function createRawFidBatchItem(input: {
  file: File
  label?: string
  sourceDir?: string | null
  fileCount?: number | null
  uncompressedBytes?: number | null
}): RawFidBatchItem {
  const preflight = preflightRawFidArchive({
    name: input.file.name,
    size: input.file.size,
    uncompressedBytes: input.uncompressedBytes ?? null,
    fileCount: input.fileCount ?? null,
  })
  return {
    id: nextRawFidBatchItemId(),
    file: input.file,
    label: input.label?.trim() || input.file.name,
    sourceDir: input.sourceDir ?? null,
    fileCount: input.fileCount ?? null,
    uncompressedBytes: input.uncompressedBytes ?? null,
    status: preflight.ok ? "queued" : "blocked",
    mode: null,
    error: preflight.ok ? null : preflight.reason,
    startedAt: null,
    durationMs: null,
    result: null,
  }
}

/** A dataset that was refused before any upload — the row exists to explain why. */
export function createBlockedRawFidBatchItem(input: {
  label: string
  reason: string
  sourceDir?: string | null
  fileCount?: number | null
  uncompressedBytes?: number | null
}): RawFidBatchItem {
  return {
    id: nextRawFidBatchItemId(),
    // A placeholder stands in for the archive we deliberately never built. The item can never
    // run, so nothing reads it — but every row having a file keeps the rest of the code simple.
    file: new File([], `${input.label || "dataset"}.zip`),
    label: input.label,
    sourceDir: input.sourceDir ?? null,
    fileCount: input.fileCount ?? null,
    uncompressedBytes: input.uncompressedBytes ?? null,
    status: "blocked",
    mode: null,
    error: input.reason,
    startedAt: null,
    durationMs: null,
    result: null,
  }
}

export type RawFidBatchFailure = {
  status: Extract<RawFidBatchStatus, "failed" | "cancelled" | "unconfirmed">
  message: string
  /** True when moving on to the next dataset cannot possibly help. */
  stopsRun: boolean
}

function isAbortError(err: unknown): boolean {
  if (typeof DOMException !== "undefined" && err instanceof DOMException) return err.name === "AbortError"
  return err instanceof Error && err.name === "AbortError"
}

function statusOf(err: unknown): number | null {
  if (err && typeof err === "object" && typeof (err as { status?: unknown }).status === "number") {
    return (err as { status: number }).status
  }
  return null
}

/**
 * Decide what one dataset's failure means for the dataset and for the rest of the run.
 *
 * The distinction that matters most is the timeout. When the wait for a result runs out, the
 * analysis was very likely still going and its record is kept either way — so recording that as
 * "failed" would tell the reviewer something untrue about their data. It gets its own state.
 *
 * The other job is not burning through fifty datasets against a refusal that will repeat
 * identically every time: a closed product, a signed-out session, or a request-rate limit stops
 * the run once instead of failing every row.
 *
 * `displayMessage` is the already-sanitized text from the caller's error formatter — this stays
 * out of the business of turning errors into prose.
 */
export function classifyRawFidBatchFailure(err: unknown, displayMessage: string): RawFidBatchFailure {
  if (isAbortError(err)) {
    return { status: "cancelled", message: "Stopped before it finished.", stopsRun: false }
  }

  const status = statusOf(err)

  if (status === 504) {
    return {
      status: "unconfirmed",
      message:
        "The wait for a result ran out. This dataset was probably still being analyzed, and its run is kept either way — check the run list before running it again.",
      stopsRun: false,
    }
  }
  if (status === 401 || status === 403) {
    return { status: "failed", message: displayMessage, stopsRun: true }
  }
  if (status === 429) {
    return {
      status: "failed",
      message: "Too many requests in a short time.",
      stopsRun: true,
    }
  }
  if (status === 404) {
    return { status: "failed", message: displayMessage, stopsRun: true }
  }
  return { status: "failed", message: displayMessage, stopsRun: false }
}

/** A status that stopped short of a result, so re-running it is meaningful. */
export function isRawFidBatchItemRunnable(item: RawFidBatchItem): boolean {
  return item.status === "queued" || item.status === "failed" || item.status === "cancelled" || item.status === "unconfirmed"
}

export function summarizeRawFidBatch(items: readonly RawFidBatchItem[]): RawFidBatchCounts {
  const counts: RawFidBatchCounts = {
    total: items.length,
    queued: 0,
    running: 0,
    done: 0,
    failed: 0,
    cancelled: 0,
    blocked: 0,
    unconfirmed: 0,
    runnable: 0,
  }
  for (const item of items) {
    counts[item.status] += 1
    if (isRawFidBatchItemRunnable(item)) counts.runnable += 1
  }
  return counts
}

export type RawFidBatchItemFacts = {
  /** The vendor the analyzer actually recognised — never what was requested. */
  vendorDetected: string | null
  nucleus: string | null
  /** Which experiment folder inside the archive was analyzed, when reported. */
  datasetRoot: string | null
  pointCount: number | null
  peakCount: number | null
  fieldMhz: number | null
  processingPreset: string | null
  sha256: string | null
  warnings: string[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function readString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim()
  }
  return null
}

function readPositiveNumber(...values: unknown[]): number | null {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value) && value > 0) return value
  }
  return null
}

/**
 * The handful of facts a queue row shows, read straight off one analysis response.
 *
 * Everything is read defensively and every field may come back null: the two analyses return
 * different envelopes, and a row that renders "—" is honest where an invented default is not.
 * `vendorDetected` in particular is read only from the response — the vendor sent with a request
 * selects no reader, so echoing it back would claim something that was never checked.
 */
export function readRawFidBatchItemFacts(payload: unknown): RawFidBatchItemFacts {
  const empty: RawFidBatchItemFacts = {
    vendorDetected: null,
    nucleus: null,
    datasetRoot: null,
    pointCount: null,
    peakCount: null,
    fieldMhz: null,
    processingPreset: null,
    sha256: null,
    warnings: [],
  }
  if (!isRecord(payload)) return empty

  const metadata = isRecord(payload.metadata) ? payload.metadata : {}
  const inventory = isRecord(payload.file_inventory)
    ? payload.file_inventory
    : isRecord(metadata.file_inventory)
      ? metadata.file_inventory
      : {}
  const peaks = Array.isArray(payload.peaks) ? payload.peaks : null
  const rawWarnings = payload.warnings
  const warnings = Array.isArray(rawWarnings)
    ? rawWarnings.map(String)
    : typeof rawWarnings === "string" && rawWarnings.trim()
      ? [rawWarnings]
      : []

  return {
    vendorDetected: readString(payload.vendor_detected, metadata.vendor_detected),
    nucleus: readString(payload.nucleus, metadata.nucleus),
    datasetRoot: readString(inventory.dataset_root, metadata.dataset_root),
    pointCount: readPositiveNumber(payload.point_count, metadata.point_count),
    peakCount: peaks ? peaks.length : null,
    fieldMhz: readPositiveNumber(payload.field_mhz, metadata.field_mhz),
    processingPreset: readString(payload.processing_preset, metadata.selected_preset),
    sha256: readString(payload.raw_file_sha256, payload.raw_sha256, payload.sha256, metadata.sha256),
    warnings,
  }
}

/** Human byte size for queue copy. Mirrors the folder-drop formatter so both read alike. */
export function formatBatchBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B"
  const units = ["B", "KB", "MB", "GB"]
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value >= 10 || unit === 0 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`
}

/** Elapsed time for a row. Seconds until a minute, then m:ss — a run is tens of seconds. */
export function formatBatchDuration(ms: number | null): string {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return "—"
  const totalSeconds = Math.round(ms / 1000)
  if (totalSeconds < 60) return `${totalSeconds}s`
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}m ${String(seconds).padStart(2, "0")}s`
}

/**
 * How much longer the rest of the queue should take, from what the finished items actually cost.
 *
 * Median rather than mean: one dense spectrum among twenty ordinary ones should not stretch the
 * whole estimate. Returns null until something has finished — guessing before there is evidence
 * is how a progress estimate loses its credibility.
 */
export function estimateRemainingMs(items: readonly RawFidBatchItem[]): number | null {
  const finished = items
    .filter((item) => item.status === "done" && item.durationMs != null)
    .map((item) => item.durationMs as number)
    .sort((a, b) => a - b)
  if (finished.length === 0) return null
  const middle = Math.floor(finished.length / 2)
  const median =
    finished.length % 2 === 0 ? (finished[middle - 1] + finished[middle]) / 2 : finished[middle]
  const pending = items.filter((item) => item.status === "queued" || item.status === "running").length
  if (pending === 0) return null
  return median * pending
}

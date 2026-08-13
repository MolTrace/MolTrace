/**
 * Drop a vendor NMR dataset FOLDER (Bruker, Varian/Agilent) straight onto the raw-FID
 * uploader — the MestReNova-style workflow — instead of zipping it by hand first.
 *
 * The backend's raw-FID endpoint takes a `.zip`/`.tar.gz` archive and locates the dataset by
 * grouping archive members per directory and scoring each one (Bruker wants `fid` + `acqus`,
 * Varian/Agilent wants `fid` + `procpar`). So the browser walks the dropped directory, keeps the
 * relative paths intact, and zips it client-side. The upload contract is unchanged — the server
 * still receives exactly one archive.
 */
import { zip, type Zippable } from "fflate"

/** One file from a dropped folder, with its path RELATIVE to the dropped root. */
export type VendorFolderEntry = {
  /** e.g. "Sample/Raw/34/acqus" — POSIX separators, no leading slash. */
  path: string
  file: File
}

export type VendorKind = "bruker" | "varian" | "unknown"

export type VendorExperiment = {
  /** Directory holding the dataset files ("" when they sit at the dropped root). */
  dir: string
  kind: VendorKind
  /** Basenames present in that directory (lower-cased). */
  files: string[]
}

export type VendorFolderDetection = {
  kind: VendorKind
  experiments: VendorExperiment[]
  fileCount: number
  totalBytes: number
  /** True when at least one directory looks like a processable dataset. */
  usable: boolean
  /** Plain-language reason when not usable, else null. */
  reason: string | null
}

// Mirrors the backend's required sets (see fid.py `_REQUIRED_BRUKER_FILES` / `_REQUIRED_VARIAN_FILES`).
const REQUIRED_BRUKER = ["fid", "acqus"] as const
const REQUIRED_VARIAN = ["fid", "procpar"] as const

/** Junk the OS/vendor tooling sprinkles around that must never reach the archive. */
const IGNORED_BASENAMES = new Set([".ds_store", "thumbs.db", "desktop.ini", ".localized"])

function isIgnoredPath(path: string): boolean {
  const parts = path.split("/")
  const base = (parts[parts.length - 1] ?? "").toLowerCase()
  if (IGNORED_BASENAMES.has(base)) return true
  if (base.startsWith("._")) return true // macOS AppleDouble resource forks
  return parts.some((p) => p === "__MACOSX")
}

/**
 * Compare two dataset paths the way a chemist reads them: digit runs as numbers, everything else
 * as case-insensitive text. `Sample/2` sorts before `Sample/10`, which a plain `localeCompare` reverses.
 */
export function compareNaturalPath(a: string, b: string): number {
  const chunks = (value: string) => value.split(/(\d+)/).filter((part) => part !== "")
  const left = chunks(a)
  const right = chunks(b)
  for (let i = 0; i < Math.min(left.length, right.length); i++) {
    const x = left[i]
    const y = right[i]
    const xNumeric = /^\d+$/.test(x)
    const yNumeric = /^\d+$/.test(y)
    if (xNumeric && yNumeric) {
      // Compare as numbers, but fall back to length/text for runs too long for a safe integer.
      const nx = Number(x)
      const ny = Number(y)
      if (Number.isSafeInteger(nx) && Number.isSafeInteger(ny)) {
        if (nx !== ny) return nx - ny
        continue
      }
      const stripped = (v: string) => v.replace(/^0+(?=\d)/, "")
      const sx = stripped(x)
      const sy = stripped(y)
      if (sx.length !== sy.length) return sx.length - sy.length
      if (sx !== sy) return sx < sy ? -1 : 1
      continue
    }
    if (xNumeric !== yNumeric) return xNumeric ? -1 : 1
    const compared = x.localeCompare(y, undefined, { sensitivity: "base" })
    if (compared !== 0) return compared
  }
  return left.length - right.length
}

function dirOf(path: string): string {
  const i = path.lastIndexOf("/")
  return i < 0 ? "" : path.slice(0, i)
}

function baseOf(path: string): string {
  const i = path.lastIndexOf("/")
  return (i < 0 ? path : path.slice(i + 1)).toLowerCase()
}

/**
 * Group entries per directory and score each the way the backend does, so the UI can tell the
 * chemist whether the drop is processable BEFORE spending time zipping and uploading it.
 */
export function detectVendorDataset(entries: VendorFolderEntry[]): VendorFolderDetection {
  const kept = entries.filter((e) => !isIgnoredPath(e.path))
  const byDir = new Map<string, Set<string>>()
  let totalBytes = 0
  for (const e of kept) {
    totalBytes += e.file.size
    const d = dirOf(e.path)
    const set = byDir.get(d)
    if (set) set.add(baseOf(e.path))
    else byDir.set(d, new Set([baseOf(e.path)]))
  }

  const experiments: VendorExperiment[] = []
  for (const [dir, names] of byDir) {
    const hasBruker = REQUIRED_BRUKER.every((n) => names.has(n))
    const hasVarian = REQUIRED_VARIAN.every((n) => names.has(n))
    if (!hasBruker && !hasVarian) continue
    experiments.push({
      dir,
      // A directory with fid+acqus is Bruker; fid+procpar is Varian/Agilent.
      kind: hasBruker ? "bruker" : "varian",
      files: [...names].sort(),
    })
  }
  // Natural order, so Bruker expnos run 1, 2, 10 rather than 1, 10, 2. A chemist numbers expnos
  // as numbers, and the queue order is the order the results appear in — a plain string sort puts
  // experiment 10 above experiment 2 and makes a series look shuffled.
  experiments.sort((a, b) => compareNaturalPath(a.dir, b.dir))

  const kinds = new Set(experiments.map((e) => e.kind))
  const kind: VendorKind = kinds.size === 1 ? [...kinds][0]! : experiments.length > 0 ? "unknown" : "unknown"

  if (kept.length === 0) {
    return { kind: "unknown", experiments: [], fileCount: 0, totalBytes: 0, usable: false, reason: "The folder is empty." }
  }
  if (experiments.length === 0) {
    return {
      kind: "unknown",
      experiments: [],
      fileCount: kept.length,
      totalBytes,
      usable: false,
      reason:
        "No Bruker or Varian/Agilent dataset found — a processable folder contains a raw 'fid' file next to 'acqus' (Bruker) or 'procpar' (Varian/Agilent).",
    }
  }
  return { kind, experiments, fileCount: kept.length, totalBytes, usable: true, reason: null }
}

/** One experiment from a dropped folder, packaged as its own upload. */
export type VendorExperimentBundle = {
  /** The experiment directory this bundle came from ("" when it sat at the dropped root). */
  dir: string
  kind: VendorKind
  /** Every file that belongs to this experiment, relative paths untouched. */
  entries: VendorFolderEntry[]
  fileCount: number
  /** Uncompressed bytes — the figure the server measures during extraction. */
  totalBytes: number
  /** Distinct, filesystem-safe archive name derived from the FULL dir path. */
  archiveName: string
}

/**
 * Which experiment owns a file — the LONGEST matching experiment directory.
 *
 * "Most specific wins" is what keeps a nested dataset out of its parent's archive. Matching on
 * `dir + "/"` (separator included) also stops `Raw/3` from claiming `Raw/34/fid`. A root-level
 * experiment (`dir === ""`) owns everything no deeper experiment claims, which is how a Bruker
 * `pdata/1/procs` — its own directory bucket, never an experiment itself — still rides along.
 */
function ownerDirFor(path: string, dirs: readonly string[]): string | null {
  let best: string | null = null
  for (const dir of dirs) {
    if (dir !== "" && !path.startsWith(`${dir}/`)) continue
    if (best === null || dir.length > best.length) best = dir
  }
  return best
}

/**
 * Name a per-experiment archive from its FULL directory path.
 *
 * The leaf alone collides the moment two roots share an experiment number (`A/1` and `B/1` both
 * become `1.zip`), and the archive name is what the chemist reads in the queue — so it has to
 * say which experiment it is. `/` is outside the allowed class, so the sanitizer flattens the
 * path and cannot emit a traversal. The clamp keeps the TAIL because that is the specific end.
 */
export function experimentArchiveName(dir: string, fallback = "raw_fid_experiment"): string {
  const flattened = dir.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[_.]+|[_.]+$/g, "")
  const clamped = flattened.length > 120 ? flattened.slice(flattened.length - 120) : flattened
  return `${clamped || fallback}.zip`
}

/**
 * Split one dropped folder into ONE BUNDLE PER EXPERIMENT — the MestReNova behaviour, where a
 * folder of twenty expnos opens as twenty spectra rather than one.
 *
 * This matters beyond convenience: the server keeps only the single best-scoring dataset in an
 * archive and picks it by path depth then lexicographic order, so every other experiment in a
 * combined archive is silently invisible, and a mixed-vendor folder routes them all through one
 * vendor reader. One archive per experiment removes both problems, and keeps each upload under
 * the server's per-archive extraction caps.
 *
 * Zipping is deliberately NOT done here — the caller zips one bundle at a time so a large folder
 * never has every archive resident at once.
 */
export function splitVendorFolderByExperiment(
  entries: VendorFolderEntry[],
): VendorExperimentBundle[] {
  const kept = entries.filter((e) => !isIgnoredPath(e.path))
  const detection = detectVendorDataset(entries)
  if (detection.experiments.length === 0) return []

  const dirs = detection.experiments.map((x) => x.dir)
  const grouped = new Map<string, VendorFolderEntry[]>()
  for (const entry of kept) {
    const owner = ownerDirFor(entry.path, dirs)
    // A file under no experiment at all (stray notes beside the datasets) is not part of any
    // dataset and is left out rather than padding an arbitrary neighbour's archive.
    if (owner === null) continue
    const bucket = grouped.get(owner)
    if (bucket) bucket.push(entry)
    else grouped.set(owner, [entry])
  }

  const usedNames = new Map<string, number>()
  const bundles: VendorExperimentBundle[] = []
  for (const experiment of detection.experiments) {
    const own = grouped.get(experiment.dir) ?? []
    if (own.length === 0) continue
    const base = experimentArchiveName(experiment.dir)
    const seen = usedNames.get(base) ?? 0
    usedNames.set(base, seen + 1)
    // The sanitizer is many-to-one ("Sample 1" and "Sample#1" both flatten to Sample_1), so distinctness
    // has to be enforced here rather than assumed from the path being distinct.
    const archiveName = seen === 0 ? base : base.replace(/\.zip$/, `-${seen + 1}.zip`)
    bundles.push({
      dir: experiment.dir,
      kind: experiment.kind,
      entries: own,
      fileCount: own.length,
      totalBytes: own.reduce((sum, e) => sum + e.file.size, 0),
      archiveName,
    })
  }
  return bundles
}

/** Recursively read a dropped directory entry into flat, relative-path entries. */
async function readDirectoryEntry(
  entry: FileSystemDirectoryEntry,
  prefix: string,
  out: VendorFolderEntry[],
): Promise<void> {
  const reader = entry.createReader()
  // readEntries() returns at most ~100 per call, so it must be drained in a loop.
  for (;;) {
    const batch: FileSystemEntry[] = await new Promise((resolve, reject) =>
      reader.readEntries((r) => resolve(r as FileSystemEntry[]), reject),
    )
    if (batch.length === 0) break
    for (const child of batch) {
      const path = prefix ? `${prefix}/${child.name}` : child.name
      if (child.isDirectory) {
        await readDirectoryEntry(child as FileSystemDirectoryEntry, path, out)
      } else {
        const file = await new Promise<File>((resolve, reject) =>
          (child as FileSystemFileEntry).file(resolve, reject),
        )
        out.push({ path, file })
      }
    }
  }
}

/**
 * Does this drop contain a DIRECTORY? Synchronous on purpose: it lets the caller keep the ordinary
 * single-file drop fully synchronous and only pay an async round-trip for a real folder.
 * (`webkitGetAsEntry` must be called while the drop event is still being handled.)
 */
export function dataTransferHasDirectory(dataTransfer: DataTransfer): boolean {
  for (const item of Array.from(dataTransfer.items ?? [])) {
    if (item.kind !== "file") continue
    if (typeof item.webkitGetAsEntry !== "function") continue
    if (item.webkitGetAsEntry()?.isDirectory) return true
  }
  return false
}

/**
 * Pull folder contents out of a drop event. Returns [] when the drop carried no directory, so the
 * caller can fall back to its existing single-file handling.
 */
export async function vendorFolderEntriesFromDataTransfer(
  dataTransfer: DataTransfer,
): Promise<VendorFolderEntry[]> {
  const items = Array.from(dataTransfer.items ?? [])
  const roots: FileSystemDirectoryEntry[] = []
  for (const item of items) {
    if (item.kind !== "file") continue
    // webkitGetAsEntry is the only way to see a DIRECTORY in a drop; dataTransfer.files hides it.
    const entry = typeof item.webkitGetAsEntry === "function" ? item.webkitGetAsEntry() : null
    if (entry?.isDirectory) roots.push(entry as FileSystemDirectoryEntry)
  }
  if (roots.length === 0) return []
  const out: VendorFolderEntry[] = []
  for (const root of roots) await readDirectoryEntry(root, root.name, out)
  return out
}

/** Entries from a `<input type="file" webkitdirectory>` selection. */
export function vendorFolderEntriesFromFileList(files: FileList | File[]): VendorFolderEntry[] {
  const out: VendorFolderEntry[] = []
  for (const file of Array.from(files)) {
    const rel = (file as File & { webkitRelativePath?: string }).webkitRelativePath
    out.push({ path: rel && rel.length > 0 ? rel : file.name, file })
  }
  return out
}

/** Name the generated archive after the dropped root folder. */
export function archiveNameForEntries(entries: VendorFolderEntry[], fallback = "raw_fid_folder"): string {
  const first = entries.find((e) => e.path.includes("/"))?.path ?? entries[0]?.path ?? ""
  const root = first.split("/")[0] ?? ""
  const safe = (root || fallback).replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^_+|_+$/g, "")
  return `${safe || fallback}.zip`
}

/**
 * Zip the folder client-side, preserving relative paths so the backend's per-directory dataset
 * detection sees the same layout the instrument wrote.
 */
export async function zipVendorFolder(
  entries: VendorFolderEntry[],
  options: { name?: string; onProgress?: (done: number, total: number) => void } = {},
): Promise<File> {
  const kept = entries.filter((e) => !isIgnoredPath(e.path))
  if (kept.length === 0) throw new Error("No usable files were found in that folder.")

  const tree: Zippable = {}
  let done = 0
  for (const entry of kept) {
    const buf = new Uint8Array(await entry.file.arrayBuffer())
    // fflate builds nested folders from "a/b/c" keys, which is exactly the layout we want.
    tree[entry.path] = buf
    done += 1
    options.onProgress?.(done, kept.length)
  }

  const zipped = await new Promise<Uint8Array>((resolve, reject) => {
    zip(tree, { level: 6 }, (err, data) => (err ? reject(err) : resolve(data)))
  })

  const name = options.name ?? archiveNameForEntries(kept)
  // Copy into a fresh ArrayBuffer so the Blob never aliases a SharedArrayBuffer-backed view.
  const bytes = new Uint8Array(zipped.length)
  bytes.set(zipped)
  return new File([bytes], name, { type: "application/zip" })
}

/** Human-readable byte size for the drop summary. */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B"
  const units = ["B", "KB", "MB", "GB"]
  let v = bytes
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i += 1
  }
  return `${v >= 10 || i === 0 ? Math.round(v) : v.toFixed(1)} ${units[i]}`
}

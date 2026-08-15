/**
 * Read what the SPECTROMETER recorded — nucleus, solvent, field — out of a dropped dataset,
 * before anything is uploaded.
 *
 * Every Bruker `acqus` carries `##$NUC1=` and `##$SOLVENT=`, and every Varian/Agilent `procpar`
 * carries `tn` and `solvent`. The analyzer has always read them (see `_resolve_raw_fid_nucleus`
 * and `_resolve_raw_fid_solvent`), but only on the far side of an upload — so the setup form
 * showed whatever it was last left on, and a chemist learned the file was 13C after processing it
 * as 1H. These are plain text files sitting in the drop, so the browser can read them the moment
 * the folder lands and show the truth up front.
 *
 * TWO RULES THIS MODULE EXISTS TO KEEP HONEST, both taken from the analyzer rather than invented:
 *
 *   NUCLEUS — the FILE wins. `_resolve_raw_fid_nucleus` consults NUC1/TN first and falls back to
 *   the request, so a form set to 1H over a 13C dataset does not change how it is read. Reflecting
 *   the detected value into the toggle is therefore not a guess about what should happen; it is
 *   showing what already will.
 *
 *   SOLVENT — the FORM wins. `_resolve_raw_fid_solvent` returns the requested solvent whenever one
 *   was supplied and reads acqus only when it was blank, deliberately: someone re-running an old
 *   dataset in a different solvent is correcting the file, not contradicting themselves. So a
 *   detected solvent must never overwrite a solvent the session already holds. It is reported, and
 *   a disagreement is named, because solvent selects the referencing window, the impurity library
 *   and the exchangeable-proton model — but the choice stays where the analyzer puts it.
 *
 * Getting that asymmetry backwards would produce a UI that confidently predicts the opposite of
 * what the server does, which is worse than showing nothing.
 *
 * Nothing here canonicalises a solvent name. `canonical_solvent` and its profile table live on the
 * analyzer side; duplicating that mapping in the browser would give it two copies to drift apart.
 * What the instrument wrote is reported verbatim, and the analyzer maps it.
 */
import { unzip, strFromU8 } from "fflate"

import type { VendorFolderEntry } from "@/src/lib/spectracheck/vendor-folder-drop"

/** Parameter files worth opening, smallest first. Anything else in the dataset is binary. */
const BRUKER_PARAM_FILES = ["acqus", "acqu"] as const
const VARIAN_PARAM_FILES = ["procpar"] as const

/**
 * Parameter files are a few KB of text. A cap keeps a corrupt or mislabelled file from being
 * pulled into memory as a string — this runs on the main thread, on a drop the chemist is
 * waiting on.
 */
const MAX_PARAM_FILE_BYTES = 4 * 1024 * 1024

/**
 * Ceiling on an archive we will open just to read its parameters.
 *
 * `unzip` needs the whole archive as one buffer, and the accepted size runs to 2 GB — so an
 * unbounded sniff would pull a gigabyte into the tab to fetch four kilobytes of text, on the drop
 * the chemist is waiting on. 64 MB is far above any real 1D FID archive (a Bruker 1D dataset is
 * a few hundred KB, and a whole folder of experiments zips to single-digit MB), so in practice
 * this only ever declines the pathological case.
 *
 * Reading only the central directory and slicing out the members would lift the ceiling entirely,
 * but that is a zip reader written by hand to populate a hint. Above this size the drop simply
 * gets no up-front readout and the analyzer reports the same facts after the run, as before.
 */
const MAX_SNIFFABLE_ARCHIVE_BYTES = 64 * 1024 * 1024

export type VendorAcquisitionFacts = {
  /** Normalized exactly as the analyzer normalizes it: "1H", "13C", "19F", "31P", or the raw label. */
  nucleus: string | null
  /** As the instrument recorded it, angle brackets stripped. NOT canonicalised — see the header. */
  solvent: string | null
  /** Spectrometer frequency in MHz (Bruker SFO1/BF1, Varian sfrq/reffrq). */
  fieldMhz: number | null
  /** Which parameter file this came from, so the UI can attribute it. */
  source: "acqus" | "procpar"
}

/** True for a nucleus this uploader's 1H/13C toggle can actually express. */
export function isOfferedNucleus(nucleus: string | null): nucleus is "1H" | "13C" {
  return nucleus === "1H" || nucleus === "13C"
}

/**
 * Port of the analyzer's `_normalize_nucleus_label`, kept deliberately line-for-line rather than
 * tidied: the point is that both sides answer identically for the same acqus, so any cleverness
 * here is a way for the two to disagree. Pinned against the Python by test.
 */
export function normalizeNucleusLabel(value: unknown): string | null {
  if (value == null) return null
  const raw = String(value).trim()
  if (!raw) return null
  const token = raw.toUpperCase().replace(/[^A-Z0-9]/g, "")
  if (["13C", "C13", "CARBON13"].some((marker) => token.includes(marker)) || token === "CARBON") {
    return "13C"
  }
  if (
    ["1H", "H1", "PROTON"].includes(token) ||
    (token.startsWith("H") && token.includes("1") && !token.includes("13"))
  ) {
    return "1H"
  }
  if (token.includes("19F") || token.includes("F19")) return "19F"
  if (token.includes("31P") || token.includes("P31")) return "31P"
  return raw
}

/** Strip the `<...>` Bruker wraps string values in, the same way the analyzer does. */
function unwrapAngleBrackets(value: string): string {
  return value.trim().replace(/^</, "").replace(/>$/, "").trim()
}

/**
 * Both vendors write a placeholder rather than leaving the solvent field empty — Bruker `<off>`
 * for an unused channel, Varian `"none"`, both of which appear in this repo's own instrument
 * fixtures. Passing those through would put the word "none" on screen labelled as the solvent the
 * instrument recorded, which is a plain misreading of the file rather than a missing value.
 */
function meaningfulSolvent(value: string | null): string | null {
  if (!value) return null
  const token = value.trim().toLowerCase()
  if (token === "" || token === "off" || token === "none" || token === "n/a") return null
  return value.trim()
}

function finitePositive(value: string | null): number | null {
  if (value == null) return null
  const n = Number.parseFloat(value)
  // Upper bound mirrors the contract's `field_mhz` (gt=0, le=2000): a parse that lands outside it
  // read something that was not a frequency, and a wrong number shown confidently is worse than none.
  return Number.isFinite(n) && n > 0 && n <= 2000 ? n : null
}

/**
 * Bruker `acqus` is JCAMP-DX: one `##$KEY= value` per line, strings in angle brackets.
 *
 * NUC1 is the OBSERVE channel specifically. NUC2..NUC8 are decoupling channels, and on a 13C
 * experiment NUC2 is routinely `<1H>` — reading "a nucleus" out of the file rather than the
 * observe channel would report a proton spectrum for every proton-decoupled carbon run.
 */
export function parseBrukerAcqus(text: string): VendorAcquisitionFacts {
  const read = (key: string): string | null => {
    // Anchored per line so `##$NUC1=` never matches inside `##$NUC10=` or a comment body.
    const match = new RegExp(`^##\\$${key}=(.*)$`, "im").exec(text)
    return match ? unwrapAngleBrackets(match[1]) || null : null
  }
  return {
    nucleus: normalizeNucleusLabel(read("NUC1")),
    solvent: meaningfulSolvent(read("SOLVENT")),
    // SFO1 is the transmitter frequency actually used; BF1 is the basic field before offset.
    fieldMhz: finitePositive(read("SFO1")) ?? finitePositive(read("BF1")),
    source: "acqus",
  }
}

/**
 * Varian/Agilent `procpar` stores each parameter as a HEADER line naming it followed by a VALUE
 * line, e.g.
 *
 *     tn 2 1 0 0 1 1 1 1 1 1
 *     1 "H1"
 *
 * The name has to be matched on a header line only. A bare first-token match also hits value
 * lines and, worse, any line of a preceding string array whose content happens to start with the
 * word — so the header is identified by its shape: the name followed by all-numeric fields.
 */
export function parseVarianProcpar(text: string): VendorAcquisitionFacts {
  const lines = text.split(/\r?\n/)
  const read = (name: string): string | null => {
    for (let i = 0; i < lines.length - 1; i++) {
      const tokens = lines[i].trim().split(/\s+/)
      if (tokens[0] !== name || tokens.length < 3) continue
      if (!tokens.slice(1).every((t) => /^-?\d+(\.\d+)?$/.test(t))) continue
      const value = lines[i + 1].trim()
      // Value line is `<count> <value>...`; a string value is quoted.
      const quoted = /"([^"]*)"/.exec(value)
      if (quoted) return quoted[1].trim() || null
      const numeric = value.split(/\s+/)[1]
      return numeric ?? null
    }
    return null
  }
  return {
    nucleus: normalizeNucleusLabel(read("tn")),
    solvent: meaningfulSolvent(read("solvent")),
    fieldMhz: finitePositive(read("sfrq")) ?? finitePositive(read("reffrq")),
    source: "procpar",
  }
}

function basenameOf(path: string): string {
  const i = path.lastIndexOf("/")
  return (i < 0 ? path : path.slice(i + 1)).toLowerCase()
}

/**
 * Read the acquisition parameters for ONE experiment out of the files that belong to it.
 *
 * Returns null rather than a half-filled record when there is no parameter file to read: an
 * absent detection leaves the form alone, which is recoverable. A fabricated one is not.
 */
export async function sniffExperimentAcquisition(
  entries: readonly VendorFolderEntry[],
): Promise<VendorAcquisitionFacts | null> {
  const find = (names: readonly string[]): VendorFolderEntry | null => {
    for (const name of names) {
      const hit = entries.find((e) => basenameOf(e.path) === name)
      if (hit && hit.file.size <= MAX_PARAM_FILE_BYTES) return hit
    }
    return null
  }
  const bruker = find(BRUKER_PARAM_FILES)
  if (bruker) return parseBrukerAcqus(await bruker.file.text())
  const varian = find(VARIAN_PARAM_FILES)
  if (varian) return parseVarianProcpar(await varian.file.text())
  return null
}

/**
 * Read the acquisition parameters out of an ALREADY-PACKAGED `.zip`, so a dropped archive gets the
 * same up-front readout a dropped folder does.
 *
 * Only the parameter members are inflated — `filter` runs before decompression, so a 200 MB
 * archive costs one central-directory scan and a few KB of text rather than being unpacked in the
 * tab. `.tar.gz`/`.tgz` are left alone deliberately: fflate can gunzip but not walk a tar, and
 * hand-rolling a tar reader to populate a hint is not worth the surface. Those archives simply get
 * no up-front readout, and the analyzer reports the same facts after the run as it always has.
 */
export async function sniffArchiveAcquisition(file: File): Promise<VendorAcquisitionFacts | null> {
  if (!/\.zip$/i.test(file.name)) return null
  if (file.size > MAX_SNIFFABLE_ARCHIVE_BYTES) return null
  let bytes: Uint8Array
  try {
    bytes = new Uint8Array(await file.arrayBuffer())
  } catch {
    return null
  }
  const wanted = new Set<string>([...BRUKER_PARAM_FILES, ...VARIAN_PARAM_FILES])
  const found = await new Promise<Record<string, Uint8Array>>((resolve) => {
    unzip(
      bytes,
      {
        filter: (f) =>
          wanted.has(basenameOf(f.name)) &&
          f.originalSize != null &&
          f.originalSize <= MAX_PARAM_FILE_BYTES,
      },
      (err, data) => resolve(err ? {} : data),
    )
  })

  // Shallowest first, then by name — the same "most likely the dataset root" ordering the
  // analyzer uses when an archive holds more than one candidate directory.
  const paths = Object.keys(found).sort((a, b) => {
    const depth = a.split("/").length - b.split("/").length
    return depth !== 0 ? depth : a.localeCompare(b)
  })
  for (const path of paths) {
    const base = basenameOf(path)
    const text = strFromU8(found[path])
    if ((BRUKER_PARAM_FILES as readonly string[]).includes(base)) return parseBrukerAcqus(text)
    if ((VARIAN_PARAM_FILES as readonly string[]).includes(base)) return parseVarianProcpar(text)
  }
  return null
}

export type AcquisitionSummary = {
  /** The single nucleus every readable experiment agrees on, else null. */
  nucleus: string | null
  /** Distinct nuclei found, in first-seen order. More than one means the folder is mixed. */
  nuclei: string[]
  /** True when the drop holds more than one nucleus — a 1H/13C pair is the ordinary case. */
  mixedNuclei: boolean
  /** The single solvent every readable experiment agrees on, else null. */
  solvent: string | null
  solvents: string[]
  fieldMhz: number | null
  /**
   * Which vendor wrote the parameter files, when they all agree — the file that exists IS the
   * vendor test, the same one the analyzer applies (`fid` + `acqus` is Bruker, `fid` + `procpar`
   * is Varian/Agilent). Null for a mixed drop.
   */
  vendor: "bruker" | "varian" | null
  /** How many experiments had a parameter file we could read. */
  readCount: number
  /** How many did not, so the UI can say the readout is partial instead of implying it is whole. */
  unreadCount: number
}

/**
 * Fold per-experiment facts into what the setup form can act on.
 *
 * A value is only offered when every experiment that could be read AGREES on it. A folder holding
 * a 1H and a 13C experiment has no single correct nucleus, and picking one — the first, the most
 * common — would silently mislabel the rest. Disagreement is reported as disagreement; the
 * analyzer then reads each archive's own acqus, so nothing is lost by the form staying out of it.
 */
export function summarizeAcquisition(
  facts: readonly (VendorAcquisitionFacts | null)[],
): AcquisitionSummary {
  const readable = facts.filter((f): f is VendorAcquisitionFacts => f != null)
  const distinct = (pick: (f: VendorAcquisitionFacts) => string | null): string[] => {
    const out: string[] = []
    for (const f of readable) {
      const v = pick(f)
      if (v && !out.includes(v)) out.push(v)
    }
    return out
  }
  const nuclei = distinct((f) => f.nucleus)
  const solvents = distinct((f) => f.solvent)
  const fields = readable.map((f) => f.fieldMhz).filter((v): v is number => v != null)
  const sources = distinct((f) => f.source)
  return {
    vendor:
      sources.length === 1 ? (sources[0] === "acqus" ? "bruker" : "varian") : null,
    nucleus: nuclei.length === 1 ? nuclei[0] : null,
    nuclei,
    mixedNuclei: nuclei.length > 1,
    solvent: solvents.length === 1 ? solvents[0] : null,
    solvents,
    // Field is reported only when it is unanimous, for the same reason as the other two.
    fieldMhz: fields.length > 0 && fields.every((v) => v === fields[0]) ? fields[0] : null,
    readCount: readable.length,
    unreadCount: facts.length - readable.length,
  }
}

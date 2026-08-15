import { describe, expect, it } from "vitest"
import { zipSync, strToU8 } from "fflate"

import {
  isOfferedNucleus,
  normalizeNucleusLabel,
  parseBrukerAcqus,
  parseVarianProcpar,
  sniffArchiveAcquisition,
  sniffExperimentAcquisition,
  summarizeAcquisition,
  type VendorAcquisitionFacts,
} from "@/src/lib/spectracheck/vendor-acquisition"
import type { VendorFolderEntry } from "@/src/lib/spectracheck/vendor-folder-drop"

/**
 * Fixtures are SYNTHETIC but format-accurate — the field order, the angle brackets, the Varian
 * header/value pairing and the ten numeric columns all match the instrument files in this repo.
 * They are written by hand rather than copied so no acquisition parameters from a real sample end
 * up committed here.
 */
const acqus = (over: Partial<Record<string, string>> = {}) =>
  [
    "##TITLE= Parameter file",
    "##JCAMPDX= 5.0",
    `##$BF1= ${over.BF1 ?? "400.1300000"}`,
    `##$NUC1= <${over.NUC1 ?? "1H"}>`,
    `##$NUC2= <${over.NUC2 ?? "off"}>`,
    `##$SFO1= ${over.SFO1 ?? "400.1324710"}`,
    `##$SOLVENT= <${over.SOLVENT ?? "CDCl3"}>`,
    "##$TD= 65536",
    "##END=",
  ].join("\n")

const procpar = (over: Partial<Record<string, string>> = {}) =>
  [
    "sfrq 1 1 0 0 1 1 1 1 1 64",
    `1 ${over.sfrq ?? "399.7439253"}`,
    "0",
    "solvent 2 2 6 0 0 2 1 11 1 64",
    `1 "${over.solvent ?? "cdcl3"}"`,
    "0",
    "tn 2 2 4 0 0 2 1 8 1 64",
    `1 "${over.tn ?? "H1"}"`,
    "0",
  ].join("\n")

const entry = (path: string, body: string): VendorFolderEntry => ({
  path,
  file: new File([body], path.split("/").pop() ?? path),
})

describe("normalizeNucleusLabel", () => {
  // The whole point of this function is to answer identically to the analyzer's
  // `_normalize_nucleus_label`, so the cases are its branches, not a sample of convenient inputs.
  it.each([
    ["1H", "1H"],
    ["H1", "1H"],
    ["proton", "1H"],
    ["13C", "13C"],
    ["C13", "13C"],
    ["carbon", "13C"],
    ["carbon13", "13C"],
    ["19F", "19F"],
    ["F19", "19F"],
    ["31P", "31P"],
    ["P31", "31P"],
  ])("maps %s to %s", (input, expected) => {
    expect(normalizeNucleusLabel(input)).toBe(expected)
  })

  it("passes an unrecognised label through rather than dropping it", () => {
    // Same rule the analyzer follows: a label we cannot classify is still what the instrument
    // wrote, and discarding it loses information a chemist can act on.
    expect(normalizeNucleusLabel("29Si")).toBe("29Si")
  })

  it("returns null for absent or blank values", () => {
    expect(normalizeNucleusLabel(null)).toBeNull()
    expect(normalizeNucleusLabel(undefined)).toBeNull()
    expect(normalizeNucleusLabel("   ")).toBeNull()
  })

  it("does not claim a proton spectrum for an H-label carrying a 13", () => {
    // The analyzer's proton branch is `startswith("H") and "1" in token and "13" not in token`.
    // "H13" satisfies the first two clauses and only the third keeps it from being called 1H —
    // and the Python returns the raw label here, so this is what keeps the two sides in step.
    expect(normalizeNucleusLabel("H13")).toBe("H13")
    // "H1,13C" is caught earlier, by the 13C substring branch, and must not reach the H rule.
    expect(normalizeNucleusLabel("H1,13C")).toBe("13C")
  })
})

describe("parseBrukerAcqus", () => {
  it("reads the observe nucleus, solvent and field", () => {
    const facts = parseBrukerAcqus(acqus())
    expect(facts).toMatchObject({ nucleus: "1H", solvent: "CDCl3", source: "acqus" })
    expect(facts.fieldMhz).toBeCloseTo(400.132471, 4)
  })

  it("reads NUC1 and not NUC2 on a proton-decoupled carbon experiment", () => {
    // The failure this guards is silent and total: every 13C{1H} run in existence has NUC2=<1H>,
    // so a parser that takes "the nucleus" instead of the OBSERVE channel reports proton for all
    // of them, and the setup form would confidently contradict the file.
    const facts = parseBrukerAcqus(acqus({ NUC1: "13C", NUC2: "1H" }))
    expect(facts.nucleus).toBe("13C")
  })

  it("prefers SFO1 over BF1, and falls back to BF1 when SFO1 is unusable", () => {
    expect(parseBrukerAcqus(acqus({ SFO1: "500.1", BF1: "500.0" })).fieldMhz).toBeCloseTo(500.1, 3)
    expect(parseBrukerAcqus(acqus({ SFO1: "0", BF1: "500.0" })).fieldMhz).toBeCloseTo(500.0, 3)
  })

  it("treats the <off> placeholder as no solvent", () => {
    expect(parseBrukerAcqus(acqus({ SOLVENT: "off" })).solvent).toBeNull()
  })

  it("reads parameter LINES only, never a $$ comment that quotes one", () => {
    // acqus carries `$$` comment lines holding arbitrary text (the repo's own Bruker fixtures
    // have three apiece). Only `^` makes a key at the start of a line the sole thing that counts;
    // without it the first `##$NUC1=` anywhere in the file wins, comment included.
    const text = [
      "##TITLE= Parameter file",
      "$$ reprocessed from a template where ##$NUC1= <13C>",
      "##$NUC1= <1H>",
      "##END=",
    ].join("\n")
    expect(parseBrukerAcqus(text).nucleus).toBe("1H")
  })

  it("ignores a frequency that is not in MHz rather than reporting it", () => {
    // Some files record the transmitter frequency in Hz. 400132471 MHz is not a spectrometer;
    // showing it would be a confidently wrong number where null is simply an absent one.
    expect(parseBrukerAcqus(acqus({ SFO1: "400132471", BF1: "400.13" })).fieldMhz).toBeCloseTo(
      400.13,
      2,
    )
    expect(parseBrukerAcqus(acqus({ SFO1: "400132471", BF1: "400130000" })).fieldMhz).toBeNull()
  })

  it("reports nulls rather than inventing values for a file with no parameters", () => {
    expect(parseBrukerAcqus("##TITLE= empty\n##END=")).toEqual({
      nucleus: null,
      solvent: null,
      fieldMhz: null,
      source: "acqus",
    })
  })
})

describe("parseVarianProcpar", () => {
  it("reads tn, solvent and sfrq from the value line under each header", () => {
    const facts = parseVarianProcpar(procpar())
    expect(facts).toMatchObject({ nucleus: "1H", solvent: "cdcl3", source: "procpar" })
    expect(facts.fieldMhz).toBeCloseTo(399.7439253, 4)
  })

  it("normalizes the Varian spelling of carbon", () => {
    // Varian writes "C13" where Bruker writes "13C" — this is the real spelling in this repo's
    // own Varian fixture, and an unnormalized value would not match the 1H/13C toggle at all.
    expect(parseVarianProcpar(procpar({ tn: "C13" })).nucleus).toBe("13C")
  })

  it('treats the "none" placeholder as no solvent', () => {
    // Found in the repo's real Varian fixture. Passed through, the UI would announce that the
    // instrument recorded a solvent called "none".
    expect(parseVarianProcpar(procpar({ solvent: "none" })).solvent).toBeNull()
  })

  it("ignores a free-text line that begins with the parameter name", () => {
    // procpar string values can run across several lines, so a line inside someone's `text`
    // parameter can legitimately start with the word "tn". A header is recognised by its SHAPE —
    // the name followed by ten numeric columns — and matching on the first token alone would take
    // the prose line and then read whatever followed it as the nucleus.
    const text = [
      "text 2 2 6 0 0 2 1 11 1 64",
      '1 "acquisition notes',
      "tn was set by the automation queue",
      'run 4 of 4"',
      "0",
      procpar({ tn: "C13" }),
    ].join("\n")
    expect(parseVarianProcpar(text).nucleus).toBe("13C")
  })

  it("returns nulls when the header exists but has no value line after it", () => {
    expect(parseVarianProcpar("tn 2 2 4 0 0 2 1 8 1 64").nucleus).toBeNull()
  })
})

describe("sniffExperimentAcquisition", () => {
  it("reads a Bruker experiment", async () => {
    const facts = await sniffExperimentAcquisition([
      entry("Sample/1/fid", "binary"),
      entry("Sample/1/acqus", acqus({ NUC1: "13C" })),
    ])
    expect(facts?.nucleus).toBe("13C")
    expect(facts?.source).toBe("acqus")
  })

  it("reads a Varian experiment", async () => {
    const facts = await sniffExperimentAcquisition([
      entry("Sample/fid", "binary"),
      entry("Sample/procpar", procpar({ tn: "C13" })),
    ])
    expect(facts?.nucleus).toBe("13C")
    expect(facts?.source).toBe("procpar")
  })

  it("returns null — not a blank record — when there is no parameter file", async () => {
    // The distinction drives the UI: null leaves the form untouched, whereas an all-null record
    // would read as "we looked and the instrument recorded nothing".
    expect(await sniffExperimentAcquisition([entry("Sample/1/fid", "binary")])).toBeNull()
  })
})

describe("sniffArchiveAcquisition", () => {
  const zipFile = (tree: Record<string, string>, name = "dataset.zip") => {
    const zipped = zipSync(
      Object.fromEntries(Object.entries(tree).map(([k, v]) => [k, strToU8(v)])),
    )
    const bytes = new Uint8Array(zipped.length)
    bytes.set(zipped)
    return new File([bytes], name, { type: "application/zip" })
  }

  it("reads acqus out of a zip without unpacking the rest", async () => {
    const facts = await sniffArchiveAcquisition(
      zipFile({ "1/acqus": acqus({ NUC1: "13C", SOLVENT: "DMSO" }), "1/fid": "binary" }),
    )
    expect(facts).toMatchObject({ nucleus: "13C", solvent: "DMSO" })
  })

  it("prefers the shallowest parameter file when an archive holds several", async () => {
    // Mirrors how the analyzer picks a dataset root: depth first, then name.
    const facts = await sniffArchiveAcquisition(
      zipFile({ "acqus": acqus({ NUC1: "1H" }), "nested/deep/acqus": acqus({ NUC1: "13C" }) }),
    )
    expect(facts?.nucleus).toBe("1H")
  })

  it("returns null for a non-zip archive rather than guessing", async () => {
    // .tar.gz is deliberately unsupported here — see the module header. Null means the UI shows
    // no up-front readout, which is correct, rather than a wrong one.
    expect(await sniffArchiveAcquisition(new File(["x"], "dataset.tar.gz"))).toBeNull()
  })

  it("returns null for a corrupt zip instead of throwing into the drop handler", async () => {
    expect(await sniffArchiveAcquisition(new File(["not a zip"], "dataset.zip"))).toBeNull()
  })
})

describe("summarizeAcquisition", () => {
  const facts = (over: Partial<VendorAcquisitionFacts>): VendorAcquisitionFacts => ({
    nucleus: "1H",
    solvent: "CDCl3",
    fieldMhz: 400,
    source: "acqus",
    ...over,
  })

  it("offers a value only when every readable experiment agrees", () => {
    const s = summarizeAcquisition([facts({}), facts({})])
    expect(s.nucleus).toBe("1H")
    expect(s.solvent).toBe("CDCl3")
    expect(s.fieldMhz).toBe(400)
    expect(s.mixedNuclei).toBe(false)
  })

  it("offers NO nucleus for a mixed 1H/13C folder, and says it is mixed", () => {
    // The ordinary Bruker folder — expno 1 proton, expno 2 carbon. Picking either one would
    // mislabel the other half of the queue, and "first wins" is the tempting wrong answer.
    const s = summarizeAcquisition([facts({}), facts({ nucleus: "13C" })])
    expect(s.nucleus).toBeNull()
    expect(s.mixedNuclei).toBe(true)
    expect(s.nuclei).toEqual(["1H", "13C"])
  })

  it("withholds the field when experiments disagree on it", () => {
    expect(summarizeAcquisition([facts({}), facts({ fieldMhz: 500 })]).fieldMhz).toBeNull()
  })

  it("counts what could not be read so the readout can be called partial", () => {
    const s = summarizeAcquisition([facts({}), null, null])
    expect(s.readCount).toBe(1)
    expect(s.unreadCount).toBe(2)
    // One readable experiment still agrees with itself — a partial readout is usable, it just
    // must not be presented as covering the whole drop.
    expect(s.nucleus).toBe("1H")
  })

  it("is empty, not throwing, for a drop where nothing was readable", () => {
    const s = summarizeAcquisition([null, null])
    expect(s).toMatchObject({ nucleus: null, solvent: null, mixedNuclei: false, readCount: 0 })
  })

  it("ignores a null field on one experiment rather than calling it a disagreement", () => {
    expect(summarizeAcquisition([facts({}), facts({ fieldMhz: null })]).fieldMhz).toBe(400)
  })
})

describe("isOfferedNucleus", () => {
  it("accepts only what the 1H/13C toggle can express", () => {
    expect(isOfferedNucleus("1H")).toBe(true)
    expect(isOfferedNucleus("13C")).toBe(true)
    // A 19F dataset is read fine by the analyzer, but the toggle cannot say so — the UI has to
    // report it in words instead of silently leaving the control on 1H as though it matched.
    expect(isOfferedNucleus("19F")).toBe(false)
    expect(isOfferedNucleus(null)).toBe(false)
  })
})

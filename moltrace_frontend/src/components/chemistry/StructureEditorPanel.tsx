"use client"

import Link from "next/link"
import { useCallback, useRef, useState } from "react"
import { AlertCard } from "@/components/dashboard/alert-card"
import { Button } from "@/components/ui/button"
import { EntityPicker } from "@/components/ui/entity-picker"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { apiFetch } from "@/lib/api/client"
import { loadCompounds, loadReactionProjects } from "@/lib/ui/entity-options"
import { LazyStructureCanvas } from "@/src/components/chemistry/LazyStructureCanvas"
import type {
  StructureEditorApi,
  StructureSnapshot,
} from "@/src/components/chemistry/StructureEditor"
import { Input } from "@/components/ui/input"
import {
  attachReactionScheme,
  issueAtomIndices,
  isHeadlineWarning,
  readVerdict,
  validateStructure,
  type StructureIssue,
  type StructureVerdict,
} from "@/src/lib/chemistry/structure-validation"

/** Formats the engine reads. Extensions are a hint for the file picker only —
 *  the engine sniffs the actual content, which is why paste works too. */
const IMPORT_ACCEPT = ".mol,.rxn,.sdf,.smi,.smiles,.cxsmiles,.txt"

const IMPORT_PLACEHOLDER = `Paste a molfile, reaction (RXN), SMILES, or CXSMILES.

For example:  CC(=O)Cl.OCC>>CC(=O)OCC`

/** One warning or error. `message` is already chemist-facing — rendered verbatim, never rewritten. */
function IssueLine({ issue }: { issue: StructureIssue }) {
  const indices = issueAtomIndices(issue)
  return (
    <li className={isHeadlineWarning(issue) ? "font-medium text-foreground" : undefined}>
      {issue.message}
      {indices.length > 0 ? (
        <span className="text-muted-foreground">
          {" "}
          (atom{indices.length > 1 ? "s" : ""} {indices.join(", ")})
        </span>
      ) : null}
    </li>
  )
}

function StructureVerdictReadout({
  verdict,
  format,
}: {
  verdict: StructureVerdict
  format: StructureSnapshot["format"]
}) {
  const counts = verdict.componentCounts
  return (
    <div className="space-y-2 rounded-md border bg-muted/20 p-3">
      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
        What the chemistry service read
      </p>

      {verdict.errors.length > 0 ? (
        <AlertCard
          variant="error"
          title="This will not do as chemistry"
          description="The drawing could not be accepted as written. It cannot be attached until these are resolved."
        />
      ) : verdict.warnings.length > 0 ? (
        <AlertCard
          variant="warning"
          title="Readable, with something to look at"
          description="The structure was read, but the service changed or could not confirm part of it. Check the points below before relying on it."
        />
      ) : verdict.ok ? (
        <AlertCard
          variant="success"
          title="Read cleanly"
          description="The service read the drawing with nothing to flag."
        />
      ) : (
        <AlertCard
          variant="warning"
          title="Not accepted"
          description="The service did not accept this drawing."
        />
      )}

      {verdict.errors.length > 0 ? (
        <ul className="list-inside list-disc space-y-1 text-xs">
          {verdict.errors.map((issue, i) => (
            <IssueLine key={`${issue.code}-${i}`} issue={issue} />
          ))}
        </ul>
      ) : null}
      {verdict.warnings.length > 0 ? (
        <ul className="list-inside list-disc space-y-1 text-xs text-muted-foreground">
          {verdict.warnings.map((issue, i) => (
            <IssueLine key={`${issue.code}-${i}`} issue={issue} />
          ))}
        </ul>
      ) : null}

      {verdict.canonicalSmiles ? (
        <p className="break-all text-xs">
          <span className="text-muted-foreground">
            {/* Order-normalized for a reaction, so it is safe as an identity key — but it is NOT
                the drawn order, which normalized_block keeps. Saying which one this is avoids a
                chemist reading component order out of the wrong string. */}
            {format === "rxn" ? "Canonical reaction SMILES (components sorted): " : "Canonical SMILES: "}
          </span>
          <span className="font-mono">{verdict.canonicalSmiles}</span>
        </p>
      ) : null}
      {verdict.inchikey ? (
        <p className="break-all text-xs">
          <span className="text-muted-foreground">InChIKey: </span>
          <span className="font-mono">{verdict.inchikey}</span>
        </p>
      ) : null}
      <p className="text-xs text-muted-foreground">
        {verdict.atomCount} atoms · {verdict.bondCount} bonds
        {counts
          ? ` · ${counts.reactants} reactant${counts.reactants === 1 ? "" : "s"}, ${counts.agents} agent${counts.agents === 1 ? "" : "s"}, ${counts.products} product${counts.products === 1 ? "" : "s"}`
          : ""}
        {verdict.validatorVersion ? ` · checked by ${verdict.validatorVersion}` : ""}
      </p>
    </div>
  )
}

type Props = {
  onCapture?: (snapshot: StructureSnapshot) => void
  /** Names the surrounding module entity, so a capture is visibly the *project's*
   *  scheme rather than a drawing floating on its own. Display only. */
  contextLabel?: string
  /** The project a scheme attaches to when the panel already sits inside one. Where it is
   *  absent — the studio, which has no ambient project — the reader picks one instead. */
  reactionProjectId?: number | null
}

export function StructureEditorPanel({ onCapture, contextLabel, reactionProjectId }: Props) {
  const [open, setOpen] = useState(false)
  const [snapshot, setSnapshot] = useState<StructureSnapshot | null>(null)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [importText, setImportText] = useState("")
  const [showImport, setShowImport] = useState(false)

  // Attaching a capture to a compound in the registry — the one link into the
  // system that exists today. Reaction schemes have no home yet; see below.
  const [attachCompoundId, setAttachCompoundId] = useState<number | string | null>(null)
  const [attachBusy, setAttachBusy] = useState(false)
  const [attachError, setAttachError] = useState("")
  /** What the registry made of the structure once it had it. The attach response
   *  carries RDKit's reading — canonical form, formula, and any complaint — so
   *  the reader gets the system's verdict instead of a bare "saved". */
  const [attached, setAttached] = useState<{
    id: string
    canonicalSmiles: string
    formula: string
    warnings: string[]
  } | null>(null)

  // What the chemistry service made of the drawing. `null` means nothing has answered yet, which
  // is NOT the same as "fine" — the copy below distinguishes the two rather than defaulting to
  // reassurance.
  const [verdict, setVerdict] = useState<StructureVerdict | null>(null)
  const [verdictBusy, setVerdictBusy] = useState(false)
  const [verdictError, setVerdictError] = useState("")
  /** Guards against an older capture's response landing after a newer one. */
  const verdictSeq = useRef(0)

  // Attaching a reaction scheme to a reaction project — the home schemes previously did not have.
  const [schemeProjectId, setSchemeProjectId] = useState<number | string | null>(
    reactionProjectId ?? null,
  )
  const [schemeName, setSchemeName] = useState("")
  const [schemeBusy, setSchemeBusy] = useState(false)
  const [schemeError, setSchemeError] = useState("")
  const [attachedScheme, setAttachedScheme] = useState<{ id: number; name: string } | null>(null)

  const apiRef = useRef<StructureEditorApi | null>(null)
  // An import can be asked for before the engine has started — opening the
  // canvas is what triggers the download. Hold it and apply it on ready.
  const pendingRef = useRef<string | null>(null)

  const applyImport = useCallback(async (text: string) => {
    const api = apiRef.current
    if (!api) {
      pendingRef.current = text
      return
    }
    try {
      await api.load(text)
      setError("")
      setNotice("Imported onto the canvas.")
    } catch (err) {
      setNotice("")
      setError(
        err instanceof Error && err.message
          ? `That could not be read as a structure or reaction. ${err.message}`
          : "That could not be read as a structure or reaction.",
      )
    }
  }, [])

  const handleReady = useCallback(
    (api: StructureEditorApi) => {
      apiRef.current = api
      const pending = pendingRef.current
      pendingRef.current = null
      if (pending) void applyImport(pending)
    },
    [applyImport],
  )

  const importFromText = useCallback(() => {
    const text = importText.trim()
    if (!text) {
      setError("Paste a molfile, reaction, SMILES, or CXSMILES first.")
      return
    }
    setOpen(true)
    void applyImport(text)
  }, [importText, applyImport])

  /**
   * Ask the chemistry service what the drawing actually is.
   *
   * An unsound structure comes back 200 with ok:false — the verdict is in the body, so a thrown
   * error means the SERVICE could not be reached, not that the drawing is bad. Those two are
   * reported differently: a failure here leaves the claim at "not checked", never at "valid".
   */
  const runValidation = useCallback(async (s: StructureSnapshot) => {
    const seq = verdictSeq.current + 1
    verdictSeq.current = seq
    setVerdictBusy(true)
    setVerdictError("")
    setVerdict(null)
    try {
      const raw = await validateStructure({
        block: s.block,
        format: s.format === "rxn" ? "rxn" : "mol",
        smiles: s.smiles || "",
      })
      if (verdictSeq.current !== seq) return
      const read = readVerdict(raw)
      if (read == null) {
        setVerdictError("The checking service replied with something this page could not read.")
        return
      }
      setVerdict(read)
    } catch (err) {
      if (verdictSeq.current !== seq) return
      setVerdictError(
        err instanceof Error && err.message
          ? `The drawing could not be checked. ${err.message}`
          : "The drawing could not be checked.",
      )
    } finally {
      if (verdictSeq.current === seq) setVerdictBusy(false)
    }
  }, [])

  const attachScheme = useCallback(async () => {
    if (!snapshot) return
    const projectId = Number(schemeProjectId)
    if (!Number.isFinite(projectId) || projectId <= 0) return
    setSchemeBusy(true)
    setSchemeError("")
    try {
      const created = await attachReactionScheme(
        projectId,
        {
          block: snapshot.block,
          format: snapshot.format === "rxn" ? "rxn" : "mol",
          smiles: snapshot.smiles || "",
        },
        schemeName,
      )
      setAttachedScheme({ id: created.id, name: created.name?.trim() || "Untitled scheme" })
    } catch (err) {
      // A drawing RDKit cannot read is refused with 400 rather than stored, and that message is
      // already written for a chemist — render it as-is instead of replacing it with our own.
      // A project the reader does not own returns 404, deliberately identical to a missing one,
      // so it is not special-cased as an auth problem.
      setSchemeError(
        err instanceof Error && err.message ? err.message : "Could not attach the scheme.",
      )
    } finally {
      setSchemeBusy(false)
    }
  }, [snapshot, schemeProjectId, schemeName])

  const attachToCompound = useCallback(async () => {
    if (!snapshot || attachCompoundId == null) return
    setAttachBusy(true)
    setAttachError("")
    try {
      const created = await apiFetch<Record<string, unknown>>(
        `/compound-registry/compounds/${encodeURIComponent(String(attachCompoundId))}/structures`,
        {
          method: "POST",
          // Every value below is from the server's own enums, checked against
          // the live contract — these fields reject anything else outright, and
          // there is deliberately no "rxn" among the formats, which is the
          // registry telling us a reaction is not a compound structure.
          body: {
            structure_input: snapshot.block,
            structure_format: "mol",
            source: "user_entered",
            // The honest value, and the reason this attach is defensible at all:
            // nothing has run RDKit over this yet. Claiming "valid" here would
            // put an unchecked drawing into the registry wearing a verdict it
            // has not earned.
            validation_status: "not_checked",
            reviewer_status: "unreviewed",
            metadata_json: {
              captured_smiles: snapshot.smiles || null,
              drawn_in: "reaction_studio",
              // Provenance, not a verdict. validation_status stays "not_checked" above on
              // purpose: the structure service and the registry are different validators, and
              // one passing does not entitle us to mark the other's field. Recording what the
              // structure service said keeps that available to a reviewer without claiming it.
              structure_check: verdict
                ? {
                    ok: verdict.ok,
                    canonical_smiles: verdict.canonicalSmiles,
                    inchikey: verdict.inchikey,
                    warning_codes: verdict.warnings.map((w) => w.code),
                    error_codes: verdict.errors.map((e) => e.code),
                    validator_version: verdict.validatorVersion,
                  }
                : null,
            },
          },
        },
      )
      const readString = (v: unknown): string => (typeof v === "string" && v.trim() ? v.trim() : "")
      const warnings = Array.isArray(created?.normalization_warnings_json)
        ? created.normalization_warnings_json.filter(
            (w): w is string => typeof w === "string" && w.trim().length > 0,
          )
        : []
      setAttached({
        id: created?.id != null ? String(created.id) : "",
        canonicalSmiles: readString(created?.canonical_smiles),
        formula: readString(created?.formula),
        warnings,
      })
    } catch (err) {
      setAttachError(
        err instanceof Error && err.message
          ? `Could not attach it to that compound. ${err.message}`
          : "Could not attach it to that compound.",
      )
    } finally {
      setAttachBusy(false)
    }
  }, [snapshot, attachCompoundId, verdict])

  const importFromFile = useCallback(
    async (file: File | undefined) => {
      if (!file) return
      try {
        const text = await file.text()
        if (!text.trim()) {
          setError("That file is empty.")
          return
        }
        setImportText(text)
        setOpen(true)
        void applyImport(text)
      } catch {
        setError("That file could not be read.")
      }
    },
    [applyImport],
  )

  return (
    <div className="space-y-4">
      {error ? <AlertCard variant="error" title="Import problem" description={error} /> : null}
      {notice && !error ? <AlertCard variant="success" title="Imported" description={notice} /> : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant={open ? "ghost" : "outline"} onClick={() => setOpen((v) => !v)}>
          {open ? "Close canvas" : "Open drawing canvas"}
        </Button>
        {/* The import route the placeholder always promised, kept alongside
            drawing rather than replaced by it: most schemes already exist
            somewhere — in an ELN, a paper, a supplier record — and retyping
            them by hand is how transcription errors get in. */}
        <Button type="button" variant="outline" onClick={() => setShowImport((v) => !v)}>
          {showImport ? "Hide import" : "Import a scheme"}
        </Button>
      </div>

      {showImport ? (
        <div className="space-y-3 rounded-lg border p-3">
          <div className="space-y-1.5">
            <Label htmlFor="structure-import-text" className="text-xs">
              Paste a structure or reaction
            </Label>
            <Textarea
              id="structure-import-text"
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              rows={5}
              spellCheck={false}
              placeholder={IMPORT_PLACEHOLDER}
              className="font-mono text-xs"
            />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button type="button" size="sm" onClick={importFromText}>
              Import onto canvas
            </Button>
            <div className="flex items-center gap-2">
              <Label htmlFor="structure-import-file" className="text-xs text-muted-foreground">
                or choose a file
              </Label>
              <input
                id="structure-import-file"
                type="file"
                accept={IMPORT_ACCEPT}
                onChange={(e) => {
                  void importFromFile(e.target.files?.[0])
                  // Clear so choosing the same file twice fires again.
                  e.target.value = ""
                }}
                className="max-w-[16rem] text-xs file:mr-2 file:rounded-md file:border file:bg-background file:px-2 file:py-1 file:text-xs"
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Molfile, reaction (RXN), SMILES, and CXSMILES are all read. The file extension is only a
            hint — the contents decide.
          </p>
        </div>
      ) : null}

      {open ? (
        <LazyStructureCanvas
          onCapture={(s) => {
            setSnapshot(s)
            setError("")
            // A new drawing invalidates the previous verdict and any attach built on it.
            setAttachedScheme(null)
            setSchemeError("")
            onCapture?.(s)
            void runValidation(s)
          }}
          onError={setError}
          onReady={handleReady}
        />
      ) : (
        <p className="max-w-2xl text-xs text-muted-foreground">
          Draw structures and reaction schemes, or import one you already have. The canvas runs
          entirely in your browser — nothing is sent anywhere until you attach it.
        </p>
      )}

      {snapshot ? (
        <div className="rounded-lg border">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
              Captured {snapshot.format === "rxn" ? "reaction scheme" : "structure"}
              {contextLabel ? ` · ${contextLabel}` : ""}
            </p>
            <span className="font-mono text-[10px] text-muted-foreground">
              {snapshot.format === "rxn" ? "RXN" : "Molfile"} · {snapshot.block.split("\n").length} lines
            </span>
          </div>
          <div className="space-y-3 p-3">
            <div>
              <p className="text-xs text-muted-foreground">SMILES</p>
              <p className="mt-1 break-all font-mono text-xs">
                {snapshot.smiles ||
                  `Not available for this drawing — the ${snapshot.format === "rxn" ? "RXN block" : "molfile"} still is.`}
              </p>
            </div>
            {/* The verdict. Three genuinely different states, kept distinct because in a
                workspace that feeds regulatory artifacts, "we could not check" must never be
                allowed to read like "we checked and it is fine". */}
            {verdictBusy ? (
              <p className="text-xs text-muted-foreground">Checking the drawing…</p>
            ) : verdictError ? (
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">
                  Not checked — the chemistry service could not be reached, so this is still just a
                  drawing.
                </p>
                <p className="text-xs text-muted-foreground">{verdictError}</p>
                <Button type="button" size="sm" variant="outline" onClick={() => snapshot && void runValidation(snapshot)}>
                  Check again
                </Button>
              </div>
            ) : verdict ? (
              <StructureVerdictReadout verdict={verdict} format={snapshot.format} />
            ) : (
              <p className="text-xs text-muted-foreground">
                Not checked yet — no chemistry service has read this.
              </p>
            )}

            {snapshot.format === "mol" ? (
              // A single structure has a real home in the registry today, so
              // offer it rather than leaving the capture stranded in the page.
              <div className="space-y-2 border-t pt-3">
                {attachError ? (
                  <AlertCard variant="error" title="Could not attach" description={attachError} />
                ) : null}
                {attached != null ? (
                  <div className="space-y-2">
                    <AlertCard
                      variant={attached.warnings.length > 0 ? "warning" : "success"}
                      title={
                        attached.warnings.length > 0
                          ? "Attached, with something to look at"
                          : "Attached to the compound"
                      }
                      description="It is on that compound's structure list, awaiting review."
                    />
                    {/* The registry reads the structure as it stores it. Showing
                        what it made of it is the whole point of attaching — a
                        silent "saved" would hide the one opinion that matters. */}
                    {attached.canonicalSmiles || attached.formula ? (
                      <div className="rounded-md border bg-muted/20 p-3 text-xs">
                        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
                          What the registry read
                        </p>
                        {attached.formula ? (
                          <p className="mt-1">
                            <span className="text-muted-foreground">Formula: </span>
                            <span className="font-mono">{attached.formula}</span>
                          </p>
                        ) : null}
                        {attached.canonicalSmiles ? (
                          <p className="mt-1 break-all">
                            <span className="text-muted-foreground">Canonical SMILES: </span>
                            <span className="font-mono">{attached.canonicalSmiles}</span>
                          </p>
                        ) : null}
                      </div>
                    ) : null}
                    {attached.warnings.length > 0 ? (
                      <ul className="list-inside list-disc space-y-1 text-xs text-muted-foreground">
                        {attached.warnings.map((w) => (
                          <li key={w}>{w}</li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ) : (
                  <>
                    <Label htmlFor="structure-attach-compound" className="text-xs">
                      Attach to a compound
                    </Label>
                    <div className="flex flex-wrap items-center gap-2">
                      <EntityPicker
                        id="structure-attach-compound"
                        value={attachCompoundId}
                        onChange={setAttachCompoundId}
                        load={loadCompounds}
                        placeholder="Choose a compound"
                        ariaLabel="Compound to attach this structure to"
                        allowClear
                        className="max-w-xs"
                      />
                      <Button
                        type="button"
                        size="sm"
                        // Now that the drawing gets checked, a structure the service refused is
                        // not offered to the registry. Before, nothing knew enough to stop it.
                        disabled={
                          attachCompoundId == null ||
                          attachBusy ||
                          verdictBusy ||
                          (verdict != null && verdict.errors.length > 0)
                        }
                        onClick={() => void attachToCompound()}
                      >
                        {attachBusy ? "Attaching…" : "Attach structure"}
                      </Button>
                      <Link
                        href="/compounds"
                        className="text-xs text-primary underline-offset-4 hover:underline"
                      >
                        Open Compounds
                      </Link>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Stored against the compound as not checked and awaiting review — the record
                      says what it is, so nothing downstream mistakes a drawing for a verified
                      structure.
                    </p>
                  </>
                )}
              </div>
            ) : (
              // A reaction is not a compound structure, so it attaches to a reaction project
              // instead. That link exists now, which is what this panel was waiting for.
              <div className="space-y-2 border-t pt-3">
                {schemeError ? (
                  // The 400 for an unreadable drawing carries a message already written for a
                  // chemist, so it is shown as sent rather than replaced.
                  <AlertCard variant="error" title="Could not attach the scheme" description={schemeError} />
                ) : null}
                {attachedScheme != null ? (
                  <AlertCard
                    variant="success"
                    title="Attached to the reaction project"
                    description={`Stored as "${attachedScheme.name}". Both the drawing as made and the normalized form are kept.`}
                  />
                ) : verdict != null && verdict.errors.length > 0 ? (
                  <p className="text-xs text-muted-foreground">
                    This scheme cannot be attached until the problems above are resolved — a drawing
                    the service cannot read is refused rather than stored.
                  </p>
                ) : (
                  <>
                    <Label htmlFor="structure-attach-scheme-name" className="text-xs">
                      Attach as a scheme on a reaction project
                    </Label>
                    <div className="flex flex-wrap items-end gap-2">
                      {reactionProjectId == null ? (
                        <EntityPicker
                          id="structure-attach-scheme-project"
                          value={schemeProjectId}
                          onChange={setSchemeProjectId}
                          load={loadReactionProjects}
                          placeholder="Choose a reaction project"
                          ariaLabel="Reaction project to attach this scheme to"
                          allowClear
                          className="max-w-xs"
                        />
                      ) : null}
                      <Input
                        id="structure-attach-scheme-name"
                        value={schemeName}
                        onChange={(e) => setSchemeName(e.target.value)}
                        placeholder="Name it, e.g. Step 3 esterification"
                        className="max-w-xs"
                      />
                      <Button
                        type="button"
                        size="sm"
                        disabled={schemeProjectId == null || schemeBusy || verdictBusy}
                        onClick={() => void attachScheme()}
                      >
                        {schemeBusy ? "Attaching…" : "Attach scheme"}
                      </Button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      The scheme keeps both the drawing exactly as you made it and the normalized
                      form the rest of the system uses, so the record shows what was drawn as well as
                      what was stored.
                    </p>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}

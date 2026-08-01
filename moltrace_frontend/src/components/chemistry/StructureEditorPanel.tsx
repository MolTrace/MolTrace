"use client"

import Link from "next/link"
import { useCallback, useRef, useState } from "react"
import { AlertCard } from "@/components/dashboard/alert-card"
import { Button } from "@/components/ui/button"
import { EntityPicker } from "@/components/ui/entity-picker"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { apiFetch } from "@/lib/api/client"
import { loadCompounds } from "@/lib/ui/entity-options"
import { LazyStructureCanvas } from "@/src/components/chemistry/LazyStructureCanvas"
import type {
  StructureEditorApi,
  StructureSnapshot,
} from "@/src/components/chemistry/StructureEditor"

/** Formats the engine reads. Extensions are a hint for the file picker only —
 *  the engine sniffs the actual content, which is why paste works too. */
const IMPORT_ACCEPT = ".mol,.rxn,.sdf,.smi,.smiles,.cxsmiles,.txt"

const IMPORT_PLACEHOLDER = `Paste a molfile, reaction (RXN), SMILES, or CXSMILES.

For example:  CC(=O)Cl.OCC>>CC(=O)OCC`

type Props = {
  onCapture?: (snapshot: StructureSnapshot) => void
  /** Names the surrounding module entity, so a capture is visibly the *project's*
   *  scheme rather than a drawing floating on its own. Display only. */
  contextLabel?: string
}

export function StructureEditorPanel({ onCapture, contextLabel }: Props) {
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
  }, [snapshot, attachCompoundId])

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
            onCapture?.(s)
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
            {/* Deliberately NOT called "validated". Nothing has checked this yet;
                saying otherwise in a workspace that feeds regulatory artifacts
                would be the wrong claim to make. */}
            <p className="text-xs text-muted-foreground">
              Not checked yet — no chemistry service has read this. It is a drawing until something
              validates it.
            </p>

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
                        disabled={attachCompoundId == null || attachBusy}
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
              // Being explicit beats a disabled button with no explanation. A
              // reaction is not a compound structure, and forcing one into that
              // list would be a category error dressed up as a feature.
              <div className="border-t pt-3">
                <p className="text-xs text-muted-foreground">
                  Reaction schemes attach to a reaction project, not to a compound — that link needs
                  the reaction service, which this build does not yet call. A single structure can
                  be attached to a compound today.
                </p>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}

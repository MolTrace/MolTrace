"use client"

import dynamic from "next/dynamic"
import { useCallback, useRef, useState } from "react"
import { AlertCard } from "@/components/dashboard/alert-card"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import type {
  StructureEditorApi,
  StructureSnapshot,
} from "@/src/components/chemistry/StructureEditor"

/**
 * Client-only, lazily-loaded wrapper around the drawing canvas.
 *
 * `ssr: false` is required, not stylistic: Ketcher reads `window` while its
 * module is evaluated, so rendering it on the server throws. The dynamic import
 * also keeps its multi-megabyte bundle off every route that never draws — it is
 * fetched the first time a reader opens the editor, and not before.
 */
const StructureEditorCanvas = dynamic(
  () => import("@/src/components/chemistry/StructureEditor").then((m) => m.StructureEditorCanvas),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[520px] items-center justify-center rounded-lg border border-dashed bg-muted/30">
        <p className="text-sm text-muted-foreground">Starting the drawing canvas…</p>
      </div>
    ),
  },
)

/** Formats the engine reads. Extensions are a hint for the file picker only —
 *  the engine sniffs the actual content, which is why paste works too. */
const IMPORT_ACCEPT = ".mol,.rxn,.sdf,.smi,.smiles,.cxsmiles,.txt"

const IMPORT_PLACEHOLDER = `Paste a molfile, reaction (RXN), SMILES, or CXSMILES.

For example:  CC(=O)Cl.OCC>>CC(=O)OCC`

type Props = {
  onCapture?: (snapshot: StructureSnapshot) => void
}

export function StructureEditorPanel({ onCapture }: Props) {
  const [open, setOpen] = useState(false)
  const [snapshot, setSnapshot] = useState<StructureSnapshot | null>(null)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [importText, setImportText] = useState("")
  const [showImport, setShowImport] = useState(false)

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
        <StructureEditorCanvas
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
              Captured in this browser only. Chemistry checks and attaching it to the project need
              the reaction service, which this build does not yet call.
            </p>
          </div>
        </div>
      ) : null}
    </div>
  )
}

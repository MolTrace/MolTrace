"use client"

import dynamic from "next/dynamic"
import { useState } from "react"
import { AlertCard } from "@/components/dashboard/alert-card"
import { Button } from "@/components/ui/button"
import type { StructureSnapshot } from "@/src/components/chemistry/StructureEditor"

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

type Props = {
  onCapture?: (snapshot: StructureSnapshot) => void
}

export function StructureEditorPanel({ onCapture }: Props) {
  const [open, setOpen] = useState(false)
  const [snapshot, setSnapshot] = useState<StructureSnapshot | null>(null)
  const [error, setError] = useState("")

  if (!open) {
    return (
      <div className="flex flex-col items-start gap-3">
        <Button type="button" variant="outline" onClick={() => setOpen(true)}>
          Open drawing canvas
        </Button>
        <p className="max-w-2xl text-xs text-muted-foreground">
          Draw structures and reaction schemes, or paste a SMILES, molfile, or reaction string. The
          canvas runs entirely in your browser — nothing is sent anywhere until you attach it.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {error ? <AlertCard variant="error" title="Canvas problem" description={error} /> : null}

      <StructureEditorCanvas
        onCapture={(s) => {
          setSnapshot(s)
          setError("")
          onCapture?.(s)
        }}
        onError={setError}
      />

      {snapshot ? (
        <div className="rounded-lg border">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
              Captured {snapshot.isReaction ? "reaction scheme" : "structure"}
            </p>
            <span className="font-mono text-[10px] text-muted-foreground">
              {snapshot.molfile.split("\n").length} lines
            </span>
          </div>
          <div className="space-y-3 p-3">
            <div>
              <p className="text-xs text-muted-foreground">SMILES</p>
              <p className="mt-1 break-all font-mono text-xs">
                {snapshot.smiles || "Not available for this drawing — the molfile still is."}
              </p>
            </div>
            {/* Deliberately NOT called "validated". Nothing has checked this yet;
                saying otherwise in a workspace that feeds regulatory artifacts
                would be the wrong claim to make. See the handoff note below. */}
            <p className="text-xs text-muted-foreground">
              Captured in this browser only. Chemistry checks and attaching it to the project need
              the reaction service, which this build does not yet call.
            </p>
          </div>
        </div>
      ) : null}

      <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(false)}>
        Close canvas
      </Button>
    </div>
  )
}

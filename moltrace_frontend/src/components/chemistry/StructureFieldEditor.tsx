"use client"

import { useCallback, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { AlertCard } from "@/components/dashboard/alert-card"
import { LazyStructureCanvas } from "@/src/components/chemistry/LazyStructureCanvas"
import type { StructureEditorApi } from "@/src/components/chemistry/StructureEditor"

type Props = {
  /** Current SMILES for the field; seeds the canvas so editing continues from it. */
  value: string
  /** Receives the SMILES the reader drew. Only fires on an explicit capture. */
  onChange: (smiles: string) => void
  disabled?: boolean
  /** Names the thing being drawn, e.g. "impurity structure". */
  label?: string
}

/**
 * Draw-a-structure for a single SMILES text field.
 *
 * Typing SMILES by hand is the failure mode this exists to remove: the notation
 * fails silently. `CN(C)N=O` is NDMA and `CN(C)NO` is a different molecule, both
 * parse, and nothing on a text input distinguishes them. Where that string goes
 * on to drive a mutagenicity or potency call, a one-character slip becomes a
 * confident wrong answer, so the structure is worth drawing and seeing.
 *
 * The canvas doubles as the check: opening the field shows what the current
 * SMILES actually is. That is deliberately in place of inline thumbnails, which
 * would mean shipping a second chemistry engine to the browser purely to make
 * pictures — and a second renderer is a second opinion about what a structure
 * looks like.
 */
export function StructureFieldEditor({ value, onChange, disabled, label = "structure" }: Props) {
  const [open, setOpen] = useState(false)
  const [error, setError] = useState("")
  const apiRef = useRef<StructureEditorApi | null>(null)

  const handleReady = useCallback(
    (api: StructureEditorApi) => {
      apiRef.current = api
      const seed = value.trim()
      if (seed) {
        void api.load(seed).catch(() => {
          // A field can hold a half-typed or invalid string — that is exactly
          // when someone reaches for the drawing tool. Start them on a blank
          // canvas rather than refusing to open.
          setError("The current text could not be read as a structure, so the canvas started empty.")
        })
      }
    },
    [value],
  )

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled}
        onClick={() => {
          setError("")
          setOpen(true)
        }}
      >
        {value.trim() ? "Edit drawing" : "Draw"}
      </Button>

      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (!next) apiRef.current = null
        }}
      >
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>Draw the {label}</DialogTitle>
            <DialogDescription>
              Capturing replaces the text in the field. Nothing is checked here — the structure is
              assessed when the form is submitted.
            </DialogDescription>
          </DialogHeader>

          {error ? <AlertCard variant="warning" title="Started empty" description={error} /> : null}

          {open ? (
            <LazyStructureCanvas
              onError={setError}
              onReady={handleReady}
              onCapture={(snapshot) => {
                if (snapshot.format === "rxn") {
                  setError("That is a reaction. This field takes a single structure.")
                  return
                }
                if (!snapshot.smiles.trim()) {
                  setError(
                    "That drawing has no plain structure form — query atoms and R-groups cannot be written as SMILES.",
                  )
                  return
                }
                onChange(snapshot.smiles.trim())
                setOpen(false)
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  )
}

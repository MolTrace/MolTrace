"use client"

import { useCallback, useRef, useState } from "react"
import "ketcher-react/dist/index.css"
import { Editor } from "ketcher-react"
import { StandaloneStructServiceProvider } from "ketcher-standalone"
import type { Ketcher } from "ketcher-core"

/**
 * The drawing surface itself.
 *
 * Deliberately NOT exported for direct use — import
 * `StructureEditorPanel` instead, which loads this lazily and client-only.
 * Ketcher touches `window` during module evaluation, so a static import from a
 * server component crashes the render; and its bundle is multi-megabyte, which
 * has no business on any route that is not actually drawing a structure.
 *
 * The Indigo chemistry engine runs in-browser (WASM) via the standalone
 * provider, so drawing needs no server round-trip. Canonicalization and
 * validation are a separate, deliberate step — see the panel below.
 */

// One provider instance for the app. Constructing it per mount would spin up a
// second Indigo worker each time the editor is opened.
const structServiceProvider = new StandaloneStructServiceProvider()

export type StructureSnapshot = {
  /** MDL molfile — the lossless form, and what the registry stores. */
  molfile: string
  /** Daylight SMILES, for display and quick comparison. Empty when unavailable. */
  smiles: string
  /** True when the canvas holds a reaction (has an arrow), not a single structure. */
  isReaction: boolean
}

type Props = {
  /** Fired whenever the reader asks to capture what they have drawn. */
  onCapture: (snapshot: StructureSnapshot) => void
  onError: (message: string) => void
  /** Called once the engine is ready, so the panel can drop its loading state. */
  onReady?: () => void
}

export function StructureEditorCanvas({ onCapture, onError, onReady }: Props) {
  const ketcherRef = useRef<Ketcher | null>(null)
  const [busy, setBusy] = useState(false)

  const handleInit = useCallback(
    (ketcher: Ketcher) => {
      ketcherRef.current = ketcher
      // Ketcher's own standalone build publishes this handle; mirroring it lets
      // the editor be driven from the console for debugging and for end-to-end
      // checks, which is otherwise impossible — the instance lives in a ref and
      // the canvas is an SVG with no addressable structure. Read-write, same as
      // upstream: this is a chemistry sandbox, not an authority. Nothing drawn
      // here is trusted until it has been through the chemistry service.
      ;(window as unknown as { ketcher?: Ketcher }).ketcher = ketcher
      onReady?.()
    },
    [onReady],
  )

  const capture = useCallback(async () => {
    const ketcher = ketcherRef.current
    if (!ketcher) {
      onError("The drawing canvas is still starting up. Try again in a moment.")
      return
    }
    setBusy(true)
    try {
      const molfile = await ketcher.getMolfile()
      // SMILES generation fails on some valid-but-exotic drawings (query atoms,
      // R-groups). That is not a reason to lose the molfile, which is the form
      // that actually round-trips — so degrade rather than reject.
      let smiles = ""
      try {
        smiles = await ketcher.getSmiles()
      } catch {
        smiles = ""
      }
      // Ask the editor rather than sniffing the molfile text: it knows whether
      // the canvas holds a reaction, and a regex over V2000/V3000 headers would
      // be guessing at two formats at once.
      const isReaction =
        typeof ketcher.containsReaction === "function" ? Boolean(ketcher.containsReaction()) : false

      if (!molfile.trim()) {
        onError("There is nothing on the canvas yet.")
        return
      }
      onCapture({ molfile, smiles, isReaction })
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not read the drawing from the canvas.")
    } finally {
      setBusy(false)
    }
  }, [onCapture, onError])

  return (
    <div className="space-y-3">
      {/* Ketcher measures its own container, so it needs a definite height. */}
      <div className="h-[520px] w-full overflow-hidden rounded-lg border">
        <Editor
          staticResourcesUrl=""
          structServiceProvider={structServiceProvider}
          errorHandler={(message: string) => onError(String(message))}
          onInit={handleInit}
        />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void capture()}
          disabled={busy}
          className="inline-flex min-h-9 items-center rounded-md border px-3 font-mono text-[11px] font-bold uppercase tracking-[0.12em] transition-colors hover:bg-muted/40 disabled:opacity-60"
          style={{ borderColor: "var(--mt-violet)" }}
        >
          {busy ? "Capturing…" : "Capture scheme"}
        </button>
        <p className="text-xs text-muted-foreground">
          Capturing takes what is on the canvas so it can be checked and attached to this project.
        </p>
      </div>
    </div>
  )
}

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
  /**
   * The lossless form, and what the registry should store: an MDL molfile for a
   * single structure, an MDL RXN block for a reaction. Which one it is, is in
   * `format` — a reaction is NOT a molfile, and asking the engine for one
   * throws outright ("cannot be saved as *.MOL due to reaction arrows").
   */
  block: string
  format: "mol" | "rxn"
  /** Daylight SMILES, for display and quick comparison. Empty when unavailable. */
  smiles: string
}

/** What the panel can do to a live canvas once the engine has started. */
export type StructureEditorApi = {
  /** Accepts molfile, RXN, SMILES, or CXSMILES — the engine sniffs the format. */
  load: (text: string) => Promise<void>
  /**
   * The drawing expressed as a query pattern.
   *
   * Separate from the SMILES on a capture, and not interchangeable with it: a query is made of
   * exactly the things — query atoms, R-groups, bond types — that make `getSmiles()` fail, which
   * is why a captured snapshot's `smiles` is empty for precisely the drawings this is for.
   */
  getSmarts: () => Promise<string>
}

type Props = {
  /** Fired whenever the reader asks to capture what they have drawn. */
  onCapture: (snapshot: StructureSnapshot) => void
  onError: (message: string) => void
  /** Called once the engine is ready, handing back the imperative entry points. */
  onReady?: (api: StructureEditorApi) => void
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
      onReady?.({
        load: async (text: string) => {
          // One entry point for every inbound format: the engine sniffs molfile
          // vs RXN vs SMILES vs CXSMILES itself, so the panel never has to guess
          // from a file extension — which lies often enough to matter.
          await ketcher.setMolecule(text)
        },
        getSmarts: async () => {
          if (typeof ketcher.getSmarts !== "function") return ""
          return (await ketcher.getSmarts()) ?? ""
        },
      })
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
      // Ask the editor which it is, then ask for THAT format. getMolfile()
      // throws on anything with a reaction arrow, so a Reaction Studio that
      // always reached for a molfile could never capture the very thing it is
      // named after.
      const isReaction =
        typeof ketcher.containsReaction === "function" ? Boolean(ketcher.containsReaction()) : false
      const format: StructureSnapshot["format"] = isReaction ? "rxn" : "mol"
      const block = isReaction ? await ketcher.getRxn() : await ketcher.getMolfile()

      // SMILES generation fails on some valid-but-exotic drawings (query atoms,
      // R-groups). That is not a reason to lose the block, which is the form
      // that actually round-trips — so degrade rather than reject.
      let smiles = ""
      try {
        smiles = await ketcher.getSmiles()
      } catch {
        smiles = ""
      }

      if (!block.trim()) {
        onError("There is nothing on the canvas yet.")
        return
      }
      onCapture({ block, format, smiles })
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

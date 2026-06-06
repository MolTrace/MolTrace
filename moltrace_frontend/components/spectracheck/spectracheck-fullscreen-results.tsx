"use client"

import { Minimize2 } from "lucide-react"
import { useEffect, useRef, type ReactNode } from "react"

import { Button } from "@/components/ui/button"

export interface SpectrumResultsFullscreenProps {
  /** When true, the wrapped results render as a full-screen in-app overlay. */
  open: boolean
  /** Invoked by the Exit control or the Escape key. */
  onClose: () => void
  /** Title shown in the full-screen header (e.g. the Step 3 result title). */
  title: string
  /** Small uppercase eyebrow above the title (e.g. "Processed 1H"). */
  eyebrow?: string
  /** Optional secondary text after the title (e.g. the source file name). */
  subtitle?: string
  /** Optional monospace tag after the subtitle (e.g. the sample id). */
  tag?: string
  /** Stable test id for the dialog shell — only present while open. */
  testId?: string
  /** The live results subtree: spectrum + every analysis panel. */
  children: ReactNode
}

/**
 * In-place full-screen wrapper for a SpectraCheck results region.
 *
 * The SAME children render whether `open` is false (inline, inside the page
 * column) or true (fixed, covering the viewport). We NEVER move the children to
 * a different parent element or portal them elsewhere — only this wrapper's own
 * classNames toggle. Because the children's parent element is stable across the
 * toggle, React keeps every node mounted: the live SpectrumViewer and all the
 * fetching/interactive analysis panels (GSD, J-couplings, region integrals,
 * shift prediction, legacy peak picks, …) preserve their state and never
 * remount or re-fetch when the user enters or leaves full screen. That is what
 * lets the full-screen view contain EVERY result with zero duplication, and
 * auto-covers any panel added to the region in future.
 *
 * `position: fixed; inset: 0` anchors to the viewport because the app-shell
 * content path has no transformed/filtered/contained ancestor.
 */
export function SpectrumResultsFullscreen({
  open,
  onClose,
  title,
  eyebrow = "Full screen · Results",
  subtitle,
  tag,
  testId = "spectrum-results-fullscreen",
  children,
}: SpectrumResultsFullscreenProps) {
  const restoreFocusRef = useRef<HTMLElement | null>(null)

  // Esc-to-close + body scroll lock + focus restore, all gated on `open`.
  useEffect(() => {
    if (!open) return

    restoreFocusRef.current = (document.activeElement as HTMLElement) ?? null

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation()
        onClose()
      }
    }
    document.addEventListener("keydown", onKeyDown)

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"

    return () => {
      document.removeEventListener("keydown", onKeyDown)
      document.body.style.overflow = previousOverflow
      // Return focus to whatever opened the overlay.
      restoreFocusRef.current?.focus?.()
    }
  }, [open, onClose])

  // SpectrumViewer self-resizes via its own ResizeObserver, but nudging a
  // window resize on toggle guarantees an immediate Plotly redraw to the new
  // width when entering/leaving full screen.
  useEffect(() => {
    if (typeof window === "undefined") return
    window.dispatchEvent(new Event("resize"))
  }, [open])

  return (
    <div
      className={open ? "fixed inset-0 z-[80] flex flex-col bg-background outline-none" : undefined}
      role={open ? "dialog" : undefined}
      aria-modal={open ? true : undefined}
      aria-label={open ? `${title} — full screen` : undefined}
      data-testid={open ? testId : undefined}
    >
      {/* Header bar — context on the left, exit control on the right. Only
          present while full screen so the inline layout is byte-for-byte
          unchanged when closed. */}
      {open ? (
        <div className="flex shrink-0 items-center justify-between gap-3 border-b bg-card px-4 py-3 sm:px-6">
          <div className="min-w-0">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
              style={{ color: "var(--mt-teal)" }}
            >
              {eyebrow}
            </p>
            <h2 className="truncate text-base font-semibold tracking-tight sm:text-lg">
              {title}
              {subtitle ? (
                <span className="ml-2 text-sm font-normal text-muted-foreground">· {subtitle}</span>
              ) : null}
              {tag ? (
                <span className="ml-2 font-mono text-xs font-normal text-muted-foreground">{tag}</span>
              ) : null}
            </h2>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onClose}
            autoFocus
            aria-label="Close full screen spectrum view"
            className="shrink-0 gap-1.5"
          >
            <Minimize2 className="h-4 w-4" aria-hidden />
            Exit full screen
          </Button>
        </div>
      ) : null}

      {/* Scroll region — fills the viewport when open; a plain passthrough when
          closed. This element and the inner container below stay mounted across
          the toggle so their descendants never remount. */}
      <div className={open ? "min-h-0 flex-1 overflow-auto" : undefined}>
        <div className={open ? "mx-auto w-full max-w-[1800px] space-y-6 p-4 sm:p-6" : "space-y-6"}>
          {children}
        </div>
      </div>
    </div>
  )
}

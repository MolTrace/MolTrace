"use client"

import { AIEvidenceQueuePanel } from "@/components/app/ai-evidence-queue"
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet"

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * The phone presentation of the AI Evidence Queue.
 *
 * The desktop panel is a 320px slab docked to the right edge. On a phone that
 * leaves nothing for the page, which is why the shell used to simply not render
 * it — and the topbar's AI Queue button did nothing at all on mobile. A sheet
 * gives the same content the full width plus, from the underlying Radix dialog,
 * the things a hand-rolled fixed `aside` never had: a backdrop, focus trapped
 * inside the panel, Escape to dismiss, body-scroll lock, and a dialog role with
 * an accessible name.
 */
export function AIEvidenceQueueSheet({ open, onOpenChange }: Props) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        // Near-full width on a phone, and `inset-y-0` (from SheetContent) pins
        // it to both edges rather than betting on a viewport-height unit, which
        // mobile Safari measures against the wrong box while the URL bar is up.
        // The panel supplies its own labelled close control in the header row, so
        // suppress the sheet's built-in one rather than stacking two close
        // buttons in the same corner.
        showClose={false}
        className="flex w-[92vw] flex-col gap-0 p-0 sm:max-w-md"
      >
        {/* The panel's own visible heading IS the dialog title, so the sheet has
            exactly one accessible name. The description is rendered here rather
            than threaded through the panel as another prop: the panel is shared
            with the desktop docked view, which is not a dialog and needs no
            description at all. sr-only because the panel's own copy already
            explains itself to anyone who can see it. */}
        <SheetDescription className="sr-only">
          Evidence items awaiting review, and recent platform activity.
        </SheetDescription>
        <AIEvidenceQueuePanel
          variant="sheet"
          titleAs={SheetTitle}
          onClose={() => onOpenChange(false)}
        />
      </SheetContent>
    </Sheet>
  )
}

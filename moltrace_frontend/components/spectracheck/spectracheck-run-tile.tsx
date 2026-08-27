"use client"

import type { LucideIcon } from "lucide-react"

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

/**
 * The single run-action tile for SpectraCheck's "Step 2 · Run" blocks.
 *
 * Extracted because the Raw FID and Processed tabs had grown two entirely
 * different tile designs for the same two verbs — every geometry and type token
 * diverged, so a chemist switching tabs re-learned the same control. Processed's
 * variant had also drifted to a ~178 px full-bleed gradient card carrying white
 * type on --mt-teal at 1.74:1 contrast, which app/globals.css already documents
 * as failing WCAG AA ("tuned for fills/icons, not type"). It was the only
 * 148px-plus gradient tile in the product.
 *
 * Geometry follows the house pattern used ~20 times elsewhere
 * (`rounded-xl border p-4 text-left`), so hierarchy is carried by fill and label
 * rather than by size. Both sections import this; neither styles its own.
 */
export type RunTileTone = "primary" | "secondary" | "experimental"

const TONE_INK: Record<RunTileTone, string> = {
  primary: "var(--mt-teal-ink)",
  secondary: "var(--mt-teal-ink)",
  experimental: "var(--mt-amber-ink)",
}

export type SpectraCheckRunTileProps = {
  /** Short verb label in the eyebrow row, e.g. "Inspect" or "Analyze". */
  eyebrow: string
  eyebrowIcon: LucideIcon
  /** Optional right-hand chip, e.g. "Recommended" or "Experimental". */
  badge?: string
  /**
   * The tile's headline AND its accessible name. Several suites query these by
   * substring (`Preview spectrum`, `Process FID`, `Inspect spectrum`,
   * `Run evidence match`, `Run GSD analysis`), so treat them as contract.
   */
  headline: string
  description: string
  tone: RunTileTone
  loading?: boolean
  disabled?: boolean
  /**
   * Why the tile is unavailable. Rendered as visible text, never a `title`: a
   * disabled control never fires its native tooltip, so a title would be
   * unreachable by mouse, keyboard and touch alike.
   */
  disabledReason?: string
  tooltip: string
  onClick?: () => void
  testId?: string
}

export function SpectraCheckRunTile({
  eyebrow,
  eyebrowIcon: EyebrowIcon,
  badge,
  headline,
  description,
  tone,
  loading = false,
  disabled = false,
  disabledReason,
  tooltip,
  onClick,
  testId,
}: SpectraCheckRunTileProps) {
  const ink = TONE_INK[tone]
  const inert = disabled || loading

  return (
    <div className="flex min-w-0 flex-col gap-1">
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            // Explicit accessible name: without it assistive tech announces the
            // whole eyebrow/badge/headline/description blob before the verb.
            aria-label={headline}
            aria-busy={loading || undefined}
            disabled={inert}
            onClick={onClick}
            data-testid={testId}
            className={cn(
              "group relative flex w-full flex-col items-start gap-2 overflow-hidden rounded-xl border p-4 text-left transition-all",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--mt-teal)] focus-visible:ring-offset-2 focus-visible:ring-offset-background",
              loading && "cursor-wait opacity-70",
              disabled && "cursor-not-allowed opacity-60",
              !inert && "hover:-translate-y-px hover:shadow-md",
              !inert && tone === "secondary" && "border-input hover:border-[color:var(--mt-teal)]/40",
              !inert && tone === "primary" && "border-[color:var(--mt-teal)]/40 hover:border-[color:var(--mt-teal)]",
              !inert && tone === "experimental" && "border-[color:var(--mt-amber)]/40 hover:border-[color:var(--mt-amber)]",
            )}
            style={{
              borderTop: `3px solid ${tone === "experimental" ? "var(--mt-amber)" : "var(--mt-teal)"}`,
              // Secondary stays unfilled so the primary action reads first
              // without needing to be physically larger.
              backgroundColor:
                tone === "primary"
                  ? "var(--mt-teal-soft)"
                  : tone === "experimental"
                    ? "var(--mt-amber-soft)"
                    : undefined,
            }}
          >
            <div className="flex w-full items-center justify-between gap-2">
              <span
                className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                style={{ color: ink }}
              >
                <EyebrowIcon className="h-3.5 w-3.5" aria-hidden />
                {eyebrow}
              </span>
              {badge ? (
                <span
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.12em]"
                  style={{ color: tone === "secondary" ? undefined : ink }}
                >
                  {badge}
                </span>
              ) : null}
            </div>
            <span className="font-mono text-base font-bold leading-tight">{headline}</span>
            <span className="text-xs text-muted-foreground">{description}</span>
          </button>
        </TooltipTrigger>
        <TooltipContent sideOffset={4} className="max-w-xs text-xs">
          {tooltip}
        </TooltipContent>
      </Tooltip>
      {disabled && disabledReason ? (
        <p className="text-[11px] text-muted-foreground">{disabledReason}</p>
      ) : null}
    </div>
  )
}

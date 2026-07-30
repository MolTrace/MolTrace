"use client"

import { useCallback, useEffect, useState, type CSSProperties, type ReactNode } from "react"
import { ChevronDown, type LucideIcon } from "lucide-react"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { cn } from "@/lib/utils"

export type DashboardSectionAccent = "teal" | "cyan" | "violet" | "amber" | "green"

export type DashboardSectionSignalTone = "neutral" | "info" | "positive" | "warning" | "critical"

/** A short live count shown in the section header, so a *collapsed* section still
 *  reports what is happening inside it. */
export type DashboardSectionSignal = {
  label: string
  tone?: DashboardSectionSignalTone
}

type DashboardSectionProps = {
  title: string
  description?: string
  icon?: LucideIcon
  defaultOpen?: boolean
  badge?: ReactNode
  accent?: DashboardSectionAccent
  eyebrow?: string
  /** Remembers this reader's expand/collapse choice across visits and reloads. */
  storageKey?: string
  signals?: DashboardSectionSignal[]
  children: ReactNode
}

const ACCENT_VAR: Record<DashboardSectionAccent, string> = {
  teal: "var(--mt-teal)",
  cyan: "var(--mt-cyan)",
  violet: "var(--mt-violet)",
  amber: "var(--mt-amber)",
  green: "var(--mt-green)",
}

/** Tinted border + soft fill, with the label kept at `text-foreground`. The vivid
 *  accents are not legible as small type (see the ink note in globals.css), and
 *  amber/red have no ink variant — so tone is carried by the chrome, not the text. */
const SIGNAL_TONE_STYLE: Record<DashboardSectionSignalTone, CSSProperties | undefined> = {
  neutral: undefined,
  info: { borderColor: "var(--mt-cyan)", backgroundColor: "var(--mt-cyan-soft)" },
  positive: { borderColor: "var(--mt-green)", backgroundColor: "var(--mt-green-soft)" },
  warning: { borderColor: "var(--mt-amber)", backgroundColor: "var(--mt-amber-soft)" },
  critical: { borderColor: "var(--mt-red)", backgroundColor: "var(--mt-red-soft)" },
}

const SECTION_OPEN_STORAGE_PREFIX = "moltrace:dashboard:section-open:"
const SET_ALL_SECTIONS_EVENT = "moltrace:dashboard:set-all-sections"

/** Returns the remembered choice, or null when there is none — or when storage is
 *  unavailable, which throws rather than returning null in Safari private browsing
 *  and in some embedded webviews. */
function readStoredOpen(storageKey: string | undefined): boolean | null {
  if (!storageKey || typeof window === "undefined") return null
  try {
    const raw = window.localStorage.getItem(`${SECTION_OPEN_STORAGE_PREFIX}${storageKey}`)
    if (raw === "1") return true
    if (raw === "0") return false
  } catch {
    /* storage unavailable — fall back to the section default */
  }
  return null
}

function writeStoredOpen(storageKey: string | undefined, open: boolean): void {
  if (!storageKey || typeof window === "undefined") return
  try {
    window.localStorage.setItem(`${SECTION_OPEN_STORAGE_PREFIX}${storageKey}`, open ? "1" : "0")
  } catch {
    /* storage unavailable — the choice simply won't survive a reload */
  }
}

/** Expands or collapses every mounted dashboard section at once. Broadcast as an
 *  event rather than threaded as props so each section stays self-contained. */
export function setAllDashboardSectionsOpen(open: boolean): void {
  if (typeof window === "undefined") return
  try {
    window.dispatchEvent(new CustomEvent(SET_ALL_SECTIONS_EVENT, { detail: open }))
  } catch {
    /* CustomEvent unsupported — the per-section triggers still work */
  }
}

export function DashboardSection({
  title,
  description,
  icon: Icon,
  defaultOpen = false,
  badge,
  accent,
  eyebrow,
  storageKey,
  signals,
  children,
}: DashboardSectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  const accentColor = accent ? ACCENT_VAR[accent] : undefined
  const signalList = signals ?? []

  // Restored after mount rather than read during render: the server cannot see
  // this reader's storage, so reading it inline would mismatch on hydration.
  useEffect(() => {
    const stored = readStoredOpen(storageKey)
    if (stored != null) setOpen(stored)
  }, [storageKey])

  useEffect(() => {
    function onSetAll(event: Event) {
      const next = (event as CustomEvent<unknown>).detail
      if (typeof next !== "boolean") return
      setOpen(next)
      writeStoredOpen(storageKey, next)
    }
    window.addEventListener(SET_ALL_SECTIONS_EVENT, onSetAll)
    return () => window.removeEventListener(SET_ALL_SECTIONS_EVENT, onSetAll)
  }, [storageKey])

  const handleOpenChange = useCallback(
    (next: boolean) => {
      setOpen(next)
      writeStoredOpen(storageKey, next)
    },
    [storageKey],
  )

  const triggerStyle: CSSProperties | undefined = accentColor
    ? { borderLeft: `2px solid ${accentColor}` }
    : undefined

  return (
    <Collapsible open={open} onOpenChange={handleOpenChange} className="space-y-4">
      <CollapsibleTrigger
        className={cn(
          "group flex min-h-11 w-full items-center justify-between gap-3 rounded-md border-b border-border/60 pb-2 pt-1 pr-1 text-left transition-colors hover:bg-muted/30",
          accentColor ? "pl-3" : "pl-1",
        )}
        style={triggerStyle}
        aria-label={`${open ? "Collapse" : "Expand"} ${title} section`}
      >
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          {eyebrow ? (
            <span
              className="font-mono text-[9px] font-bold uppercase tracking-[0.22em]"
              style={{ color: accentColor ?? "var(--mt-teal)" }}
            >
              {eyebrow}
            </span>
          ) : null}
          <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            {Icon ? (
              <Icon
                className="h-4 w-4 shrink-0"
                style={{ color: accentColor ?? "var(--mt-teal)", opacity: 0.9 }}
                aria-hidden
              />
            ) : null}
            <h2 className="font-mono text-sm font-bold uppercase tracking-[0.18em] text-foreground">
              {title}
            </h2>
            {badge ? <span className="ml-1">{badge}</span> : null}
            {signalList.map((signal) => (
              <span
                key={signal.label}
                className="rounded-full border px-2 py-0.5 text-[10px] font-medium leading-tight text-foreground"
                style={SIGNAL_TONE_STYLE[signal.tone ?? "neutral"]}
              >
                {signal.label}
              </span>
            ))}
          </div>
          {/* The right-hand description is desktop-only, so repeat it under the
              title on narrow screens instead of dropping it. */}
          {description ? (
            <p className="text-xs text-muted-foreground sm:hidden">{description}</p>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {description ? (
            <p className="hidden max-w-[24rem] text-right text-xs text-muted-foreground sm:block">
              {description}
            </p>
          ) : null}
          <ChevronDown
            className={cn(
              "h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200",
              open && "rotate-180",
            )}
            aria-hidden
          />
        </div>
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-4">{children}</CollapsibleContent>
    </Collapsible>
  )
}

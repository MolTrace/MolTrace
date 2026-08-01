"use client"

import { useCallback, useEffect, useRef, type KeyboardEvent, type ReactNode } from "react"
import { cn } from "@/lib/utils"

export type WorkspaceStageAccent = "teal" | "cyan" | "violet"

export type WorkspaceStageSection = {
  value: string
  label: string
  desc: string
  /** Live status shown on the section itself — risk level, readiness, and the
   *  like. Unlike a count, this says something the label cannot. */
  badge?: ReactNode
}

export type WorkspaceStageGroup = {
  id: string
  label: string
  sections: WorkspaceStageSection[]
}

type Props = {
  groups: WorkspaceStageGroup[]
  activeValue: string
  onSelect: (value: string) => void
  /** Names the two tiers for assistive tech, e.g. "SpectraCheck" or "Dossier". */
  label: string
  accent?: WorkspaceStageAccent
}

const ACCENT_VAR: Record<WorkspaceStageAccent, string> = {
  teal: "var(--mt-teal)",
  cyan: "var(--mt-cyan)",
  violet: "var(--mt-violet)",
}

/** Moves focus with the arrow keys inside one tier, wrapping at both ends. */
function rovingIndex(key: string, index: number, length: number): number | null {
  if (key === "ArrowRight" || key === "ArrowDown") return (index + 1) % length
  if (key === "ArrowLeft" || key === "ArrowUp") return (index - 1 + length) % length
  if (key === "Home") return 0
  if (key === "End") return length - 1
  return null
}

/**
 * Two-tier stage navigation, shared by the module workspaces.
 *
 * A workspace with a dozen-plus sections presented as one flat strip is a single
 * undifferentiated ribbon: every entry competes with every other, and the
 * pipeline the entries already encode is invisible. Splitting it in two lets the
 * primary tier carry real visual weight — that is the decision a reader makes
 * first — while the secondary tier shows only the siblings of the stage they
 * picked.
 *
 * The group is derived from `activeValue`, so deep links and programmatic jumps
 * land on the right primary tab without any extra state to keep in sync.
 */
export function WorkspaceStageNav({
  groups,
  activeValue,
  onSelect,
  label,
  accent = "teal",
}: Props) {
  const accentColor = ACCENT_VAR[accent]
  const activeGroup = groups.find((g) => g.sections.some((s) => s.value === activeValue)) ?? groups[0]
  const activeSection =
    activeGroup?.sections.find((s) => s.value === activeValue) ?? activeGroup?.sections[0]

  // Remembers where the reader was in each stage, so returning to a primary tab
  // reopens the section they left rather than resetting to the first one.
  const lastSectionByGroup = useRef<Record<string, string>>({})
  useEffect(() => {
    if (activeGroup && activeSection) lastSectionByGroup.current[activeGroup.id] = activeSection.value
  }, [activeGroup, activeSection])

  const onPrimaryKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      const index = groups.findIndex((g) => g.id === activeGroup?.id)
      const next = rovingIndex(event.key, index, groups.length)
      if (next == null) return
      event.preventDefault()
      const group = groups[next]
      const remembered = lastSectionByGroup.current[group.id]
      const target = group.sections.some((s) => s.value === remembered)
        ? remembered
        : group.sections[0].value
      onSelect(target)
      event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus()
    },
    [groups, activeGroup, onSelect],
  )

  const onSecondaryKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (!activeGroup) return
      const sections = activeGroup.sections
      const index = sections.findIndex((s) => s.value === activeValue)
      const next = rovingIndex(event.key, index, sections.length)
      if (next == null) return
      event.preventDefault()
      onSelect(sections[next].value)
      event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus()
    },
    [activeGroup, activeValue, onSelect],
  )

  if (!activeGroup) return null

  // A single-section stage has nothing to choose between, so the second tier
  // would be a row containing the tab you are already on.
  const showSecondTier = activeGroup.sections.length > 1

  return (
    <div className="space-y-3">
      <div className="min-w-0 overflow-x-auto [-webkit-overflow-scrolling:touch]">
        <div
          role="tablist"
          aria-label={`${label} stages`}
          onKeyDown={onPrimaryKeyDown}
          className="inline-flex w-max items-end gap-1 border-b border-border"
        >
          {groups.map((group) => {
            const on = group.id === activeGroup.id
            const remembered = lastSectionByGroup.current[group.id]
            const target = group.sections.some((s) => s.value === remembered)
              ? remembered
              : group.sections[0].value
            return (
              <button
                key={group.id}
                type="button"
                role="tab"
                aria-selected={on}
                tabIndex={on ? 0 : -1}
                data-testid={`stage-${group.id}`}
                onClick={() => onSelect(target)}
                className={cn(
                  "relative inline-flex min-h-11 shrink-0 items-center gap-2 whitespace-nowrap rounded-t-lg px-4 pb-2.5 pt-2 font-mono text-sm font-bold tracking-tight transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                  on ? "text-foreground" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                )}
              >
                {group.label}
                {/* Deliberately no section count. A number on a tab reads as a
                    notification badge — items waiting on you — so "Evidence
                    Inputs 5" implied five outstanding tasks rather than five
                    sections. The sections are listed directly below anyway. */}
                {/* The selected stage is marked by a bar that sits ON the shared
                    bottom border, so the tier reads as one connected surface. */}
                <span
                  aria-hidden
                  className={cn("absolute inset-x-1 -bottom-px h-0.5 rounded-full", !on && "opacity-0")}
                  style={{ backgroundColor: accentColor }}
                />
              </button>
            )
          })}
        </div>
      </div>

      {showSecondTier ? (
        <div className="min-w-0 overflow-x-auto pb-1 [-webkit-overflow-scrolling:touch]">
          <div
            role="tablist"
            aria-label={`${activeGroup.label} sections`}
            onKeyDown={onSecondaryKeyDown}
            className="inline-flex w-max items-center gap-1.5"
          >
            {activeGroup.sections.map((section) => {
              const on = section.value === activeValue
              return (
                <button
                  key={section.value}
                  type="button"
                  role="tab"
                  aria-selected={on}
                  tabIndex={on ? 0 : -1}
                  data-testid={`stage-section-${section.value}`}
                  onClick={() => onSelect(section.value)}
                  className={cn(
                    "inline-flex min-h-9 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3.5 py-1.5 font-mono text-[13px] transition-colors",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                    on
                      ? "border-transparent font-bold text-[#04080F] shadow-sm"
                      : "border-border bg-background text-muted-foreground hover:border-foreground/40 hover:bg-muted hover:text-foreground",
                  )}
                  style={on ? { backgroundColor: accentColor } : undefined}
                >
                  {section.label}
                  {section.badge}
                </button>
              )
            })}
          </div>
        </div>
      ) : null}

      {activeSection ? (
        <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">{activeSection.desc}</p>
      ) : null}
    </div>
  )
}

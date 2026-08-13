"use client"

import Link from "next/link"
import { useCallback, useEffect, useRef, type KeyboardEvent, type ReactNode } from "react"
import { cn } from "@/lib/utils"
import { useSlidingIndicator } from "./use-sliding-indicator"

export type WorkspaceStageAccent = "teal" | "cyan" | "violet"

export type WorkspaceStageSection = {
  value: string
  label: string
  desc: string
  /** Live status shown on the section itself — risk level, readiness, and the
   *  like. Unlike a count, this says something the label cannot. */
  badge?: ReactNode
  /** Set when this section is a separate route rather than a panel in the same
   *  page. Any section carrying one switches the whole nav to route mode. */
  href?: string
}

export type WorkspaceStageGroup = {
  id: string
  label: string
  sections: WorkspaceStageSection[]
}

type Props = {
  groups: WorkspaceStageGroup[]
  activeValue: string
  /** Required in panel mode; unused once sections carry an `href`. */
  onSelect?: (value: string) => void
  /** Names the two tiers for assistive tech, e.g. "SpectraCheck" or "Dossier". */
  label: string
  accent?: WorkspaceStageAccent
}

/**
 * Each accent carries the text colour that is legible ON it, because the right
 * answer flips between them. Near-black clears AA comfortably on teal (11.5:1)
 * and cyan (8.5:1), but violet is dark enough that near-black falls to 3.3:1 —
 * below AA — and needs near-white instead (5.5:1). Picking one foreground for
 * all three would fail one of them.
 */
const ACCENT: Record<WorkspaceStageAccent, { bg: string; fg: string }> = {
  teal: { bg: "var(--mt-teal)", fg: "#04080F" },
  cyan: { bg: "var(--mt-cyan)", fg: "#04080F" },
  violet: { bg: "var(--mt-violet)", fg: "#EBF4F8" },
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
  const { bg: accentBg, fg: accentFg } = ACCENT[accent]
  // Route mode: these entries are separate pages, so they render as links that
  // announce themselves with aria-current. Calling them tabs would promise
  // in-place panel switching that does not happen, and arrow-key roaming would
  // fire off a page load per keypress.
  const routeMode = groups.some((g) => g.sections.some((s) => s.href))
  const activeGroup = groups.find((g) => g.sections.some((s) => s.value === activeValue)) ?? groups[0]
  const activeSection =
    activeGroup?.sections.find((s) => s.value === activeValue) ?? activeGroup?.sections[0]

  // One indicator per tier, each travelling between its own items.
  const primaryNav = useSlidingIndicator(activeGroup?.id)
  const secondaryNav = useSlidingIndicator(activeValue)

  // Remembers where the reader was in each stage, so returning to a primary tab
  // reopens the section they left rather than resetting to the first one.
  const lastSectionByGroup = useRef<Record<string, string>>({})
  useEffect(() => {
    if (activeGroup && activeSection) lastSectionByGroup.current[activeGroup.id] = activeSection.value
  }, [activeGroup, activeSection])

  const onPrimaryKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (routeMode) return
      const index = groups.findIndex((g) => g.id === activeGroup?.id)
      const next = rovingIndex(event.key, index, groups.length)
      if (next == null) return
      event.preventDefault()
      const group = groups[next]
      const remembered = lastSectionByGroup.current[group.id]
      const target = group.sections.some((s) => s.value === remembered)
        ? remembered
        : group.sections[0].value
      onSelect?.(target)
      event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus()
    },
    [groups, activeGroup, onSelect, routeMode],
  )

  const onSecondaryKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (routeMode || !activeGroup) return
      const sections = activeGroup.sections
      const index = sections.findIndex((s) => s.value === activeValue)
      const next = rovingIndex(event.key, index, sections.length)
      if (next == null) return
      event.preventDefault()
      onSelect?.(sections[next].value)
      event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus()
    },
    [activeGroup, activeValue, onSelect, routeMode],
  )

  if (!activeGroup) return null

  // A single-section stage has nothing to choose between, so the second tier
  // would be a row containing the tab you are already on.
  const showSecondTier = activeGroup.sections.length > 1

  /**
   * ...but the SPACE is reserved whenever any stage in this nav could show that
   * row, even on the stages that do not.
   *
   * Without this the nav changes height as you move between stages, and since it
   * sits above the whole workspace, everything below it jumps. Measured on
   * Regentry, whose stages hold 1, 1, 2 and 3 sections: the nav block went 80px
   * to 136px and the content beneath it moved 56px — every time you changed
   * stage. That is the "shaky" feeling; it is not a transition problem, it is
   * the chrome resizing under the content.
   *
   * Reserving costs an empty 40px band on single-section stages. That is the
   * right trade for a workspace nav: it is furniture, and furniture that moves
   * when you look at it is worse than furniture that takes up room.
   */
  const reserveSecondTier = groups.some((g) => g.sections.length > 1)

  return (
    <div className="space-y-3">
      <div className="min-w-0 overflow-x-auto [-webkit-overflow-scrolling:touch]">
        <div
          ref={primaryNav.containerRef}
          {...(routeMode ? {} : ({ role: "tablist" } as const))}
          aria-label={`${label} stages`}
          onKeyDown={onPrimaryKeyDown}
          className="relative inline-flex w-max items-end gap-1 border-b border-border"
        >
          {/* One bar that travels, rather than a bar per tab fading in and out.
              Width animates with position so it takes the shape of whichever tab
              it lands on. */}
          {primaryNav.rect ? (
            <span
              aria-hidden
              className="pointer-events-none absolute -bottom-px left-0 h-[3px] rounded-full transition-[transform,width] duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none"
              style={{
                transform: `translateX(${primaryNav.rect.left}px)`,
                width: primaryNav.rect.width,
                backgroundColor: accentBg,
              }}
            />
          ) : null}
          {groups.map((group) => {
            const on = group.id === activeGroup.id
            const remembered = lastSectionByGroup.current[group.id]
            const target =
              group.sections.find((s) => s.value === remembered) ?? group.sections[0]
            const className = cn(
              "relative inline-flex min-h-11 shrink-0 items-center gap-2 whitespace-nowrap rounded-t-lg px-4 pb-2.5 pt-2 font-mono text-sm font-bold tracking-tight transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
              on ? "text-foreground" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
            )
            {/* Deliberately no section count. A number on a tab reads as a
                notification badge — items waiting on you — so "Evidence Inputs 5"
                implied five outstanding tasks rather than five sections. The
                sections are listed directly below anyway. */}
            const contents = group.label
            if (routeMode) {
              return (
                <Link
                  key={group.id}
                  href={target.href ?? "#"}
                  aria-current={on ? "page" : undefined}
                  data-active={on}
                  data-testid={`stage-${group.id}`}
                  className={className}
                >
                  {contents}
                </Link>
              )
            }
            return (
              <button
                key={group.id}
                type="button"
                role="tab"
                aria-selected={on}
                tabIndex={on ? 0 : -1}
                data-active={on}
                data-testid={`stage-${group.id}`}
                onClick={() => onSelect?.(target.value)}
                className={className}
              >
                {contents}
              </button>
            )
          })}
        </div>
      </div>

      {reserveSecondTier ? (
        // min-h-11 (44px), not min-h-10. The pills are 40px and `pb-1` adds 4
        // BELOW them, so a populated band measures 44 — while an empty band with
        // min-height 40 measures 40, because box-sizing folds that same padding
        // inside the reservation. Reserving 40 therefore leaves a 4px twitch,
        // which is exactly the kind of almost-fixed that reads as still broken.
        <div
          data-stage-sections-band=""
          className="min-h-11 min-w-0 overflow-x-auto pb-1 [-webkit-overflow-scrolling:touch]"
        >
          {showSecondTier ? (
          <div
            {...(routeMode ? {} : ({ role: "tablist" } as const))}
            ref={secondaryNav.containerRef}
            aria-label={`${activeGroup.label} sections`}
            onKeyDown={onSecondaryKeyDown}
            className="relative inline-flex w-max items-center gap-2"
          >
            {/* The fill itself, travelling. The pills above it stay transparent
                and only change text colour, so the selection reads as one object
                moving rather than two backgrounds cross-fading. */}
            {secondaryNav.rect ? (
              <span
                aria-hidden
                className="pointer-events-none absolute bottom-0 left-0 top-0 rounded-xl transition-[transform,width] duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none"
                style={{
                  transform: `translateX(${secondaryNav.rect.left}px)`,
                  width: secondaryNav.rect.width,
                  backgroundColor: accentBg,
                }}
              />
            ) : null}
            {activeGroup.sections.map((section) => {
              const on = section.value === activeValue
              // border-2 on BOTH states, transparent when active: the fill is the
              // travelling indicator behind the pill, so if the active pill
              // dropped its border every neighbour would shift 4px sideways the
              // moment the selection moved.
              const className = cn(
                "relative z-10 inline-flex min-h-10 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-xl border-2 px-4 py-2 font-mono text-[13px] font-medium",
                "transition-colors duration-200 ease-[cubic-bezier(0.4,0,0.2,1)] motion-reduce:transition-none",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                on
                  ? "border-transparent font-bold"
                  : "border-border bg-card text-muted-foreground hover:border-foreground/40 hover:text-foreground",
              )
              const style = on ? { color: accentFg } : undefined
              if (routeMode) {
                return (
                  <Link
                    key={section.value}
                    href={section.href ?? "#"}
                    aria-current={on ? "page" : undefined}
                    data-active={on}
                    data-testid={`stage-section-${section.value}`}
                    className={className}
                    style={style}
                  >
                    {section.label}
                    {section.badge}
                  </Link>
                )
              }
              return (
                <button
                  key={section.value}
                  type="button"
                  role="tab"
                  aria-selected={on}
                  tabIndex={on ? 0 : -1}
                  data-active={on}
                  data-testid={`stage-section-${section.value}`}
                  onClick={() => onSelect?.(section.value)}
                  className={className}
                  style={style}
                >
                  {section.label}
                  {section.badge}
                </button>
              )
            })}
          </div>
          ) : null}
        </div>
      ) : null}

      {/* min-h-[2lh] reserves TWO LINES, because these descriptions are one line
          on some sections and two on others — measured at 20px and 40px on
          Regentry — and that difference moved the whole workspace by 20px on
          every switch. Expressed in `lh` rather than a pixel value so it stays
          exactly two lines if the type scale ever changes. */}
      {activeSection ? (
        <p className="min-h-[2lh] max-w-3xl text-sm leading-relaxed text-muted-foreground">
          {activeSection.desc}
        </p>
      ) : null}
    </div>
  )
}

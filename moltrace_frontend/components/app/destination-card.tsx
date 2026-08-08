import Link from "next/link"
import { ArrowRight, ArrowUpRight, type LucideIcon } from "lucide-react"

/**
 * One destination on a module hub — Knowledge Library, AI Services, Model
 * Factory. Shared so the three cannot drift.
 *
 * WHY THE GROUP IS A PILL AND NOT A HEADING. These were laid out as one grid per
 * group, each three columns wide. Any group whose count is not a multiple of
 * three then punched a hole in the page: "Decide" held a single card alone in a
 * three-wide row, and "Assess before shipping" held four, so the fourth sat by
 * itself beside two empty slots. Ragged gaps mid-page read as something failing
 * to load.
 *
 * So the groups became pills and the cards became one continuous grid. Nine cards
 * fill three rows exactly, six fill two. A short final row is ordinary; a hole in
 * the middle is not. Grouping survives in the pill and in the accent colour,
 * which is what a reader actually scans by — and it is what the reference design
 * did in the first place.
 *
 * COLOUR ROLES, which must not be swapped: `accent` is the vivid token and fills
 * the left rule and the icon; `ink` is the AA-safe variant and colours every
 * piece of type; `soft` is the low-alpha tint behind the pill. The vivid tokens
 * sit at 2–3:1 as text on a light page and fail AA.
 */
export type Destination = {
  label: string
  href: string
  desc: string
  icon: LucideIcon
  /** Group name, shown as the pill. */
  group: string
  accent: string
  ink: string
  soft: string
  /** True when the href leaves this module — changes the arrow and the pill. */
  leavesModule?: boolean
}

export function DestinationCard({ item }: { item: Destination }) {
  const Icon = item.icon
  const Arrow = item.leavesModule ? ArrowUpRight : ArrowRight
  return (
    <Link
      href={item.href}
      className="group relative flex h-full min-w-0 flex-col rounded-xl border bg-card p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring motion-reduce:transition-none motion-reduce:hover:translate-y-0"
      style={{ borderLeftWidth: "3px", borderLeftColor: item.accent }}
    >
      <div className="flex items-center gap-2">
        {/* Icons keep the vivid accent — shapes, not type. */}
        <Icon className="h-5 w-5 shrink-0" style={{ color: item.accent }} aria-hidden />
        <h3 className="min-w-0 text-sm font-semibold" style={{ color: item.ink }}>
          {item.label}
        </h3>
        <Arrow
          className={
            "h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform duration-200 motion-reduce:transition-none " +
            (item.leavesModule
              ? "group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
              : "group-hover:translate-x-0.5")
          }
          aria-hidden
        />
      </div>

      <span
        className="mt-3 inline-block w-fit rounded-full px-2 py-0.5 text-[11px] font-medium"
        style={{ backgroundColor: item.soft, color: item.ink }}
      >
        {item.group}
        {item.leavesModule ? " · opens another module" : null}
      </span>

      <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{item.desc}</p>
    </Link>
  )
}

/** The one grid every hub uses. Continuous, so groups never punch holes in it. */
export function DestinationGrid({ items }: { items: readonly Destination[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((item) => (
        <DestinationCard key={item.href} item={item} />
      ))}
    </div>
  )
}

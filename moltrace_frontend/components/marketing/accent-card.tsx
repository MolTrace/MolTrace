import type { LucideIcon } from "lucide-react"

/**
 * The card the landing page uses wherever a set of parallel points needs to read
 * as a set: a 3px rule down the left edge in the section's accent, an icon and
 * title on one line, a tinted pill, then the point itself.
 *
 * Used by the evidence section. (It was shared with the enterprise section until
 * that became a stacked deck; the hero's version is a <Link> with a navigation
 * glyph and has always been separate on purpose.)
 *
 * TWO SURFACES. `surface` is the ordinary card on a page background. `glass` is
 * for the constellation band, where an opaque card would punch a hole in the sky
 * — it is translucent and blurred so the stars carry through, with a light
 * border instead of the theme's. Everything else about the card is identical, so
 * the two cannot drift apart.
 *
 * DELIBERATELY NOT INTERACTIVE. There is no hover lift and no arrow here: both
 * are affordances that promise a destination, and these cards have none. A card
 * that rises under the cursor and then does nothing is a small lie about what
 * the page can do.
 *
 * COLOUR ROLES, which must not be swapped:
 *   accent - the vivid brand token. Fills the left rule and the icon only.
 *   ink    - the AA-safe variant. Every piece of type on the card.
 *   soft   - the low-alpha tint behind the pill.
 * The vivid tokens sit at 2-3:1 as text on a light page and fail AA; that is the
 * entire reason the -ink variants exist.
 */
export type AccentCardProps = {
  icon: LucideIcon
  title: string
  pill: string
  desc: string
  accent: string
  ink: string
  soft: string
  tone?: "surface" | "glass"
}

export function AccentCard({
  icon: Icon,
  title,
  pill,
  desc,
  accent,
  ink,
  soft,
  tone = "surface",
}: AccentCardProps) {
  return (
    <div
      className={
        "relative h-full min-w-0 rounded-xl border p-5 " +
        (tone === "glass"
          ? "border-white/10 bg-white/[0.04] backdrop-blur-md"
          : "bg-card")
      }
      style={{ borderLeftWidth: "3px", borderLeftColor: accent }}
    >
      <div className="flex min-w-0 items-center gap-2">
        {/* Icons keep the vivid accent — they are shapes, not type. */}
        <Icon className="h-5 w-5 shrink-0" style={{ color: accent }} aria-hidden />
        <h3 className="min-w-0 text-sm font-semibold" style={{ color: ink }}>
          {title}
        </h3>
      </div>

      <span
        className="mt-3 inline-block rounded-full px-2 py-0.5 text-[11px] font-medium"
        style={{ backgroundColor: soft, color: ink }}
      >
        {pill}
      </span>

      <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{desc}</p>
    </div>
  )
}

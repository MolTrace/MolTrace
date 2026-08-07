import { Plus } from "lucide-react"

import type { FaqItem } from "@/components/seo/structured-data"

/**
 * Visible FAQ section (server component). Renders each Q&A with a native
 * <details>/<summary> disclosure so the answer text is in the initial
 * server-rendered HTML — extractable by AI/answer engines and valid for the
 * FAQPage schema emitted alongside it — while staying tidy for humans. No
 * client JS: <details> toggles natively.
 *
 * Pair with <ModuleJsonLd faqs=...> or <FaqJsonLd> so the same Q&A is both
 * visible and machine-readable.
 *
 * ON THE VISUAL TREATMENT: everything here is CSS on top of the native
 * disclosure — an editorial two-column layout, a monospace index, a rule that
 * ignites in the brand accent when an entry opens, and an ambient field behind
 * the whole section. Nothing was traded for it:
 *
 *   - still a server component, still zero client JS
 *   - still <details>/<summary>, so keyboard and screen-reader behaviour is the
 *     browser's own and the answers remain in the server HTML
 *   - still <h3> inside <summary>, because <summary> alone carries no heading
 *     semantics and these are the only question-shaped strings on the site
 *
 * There is deliberately no open/close height animation. Native <details> takes
 * its content out of flow when closed, so a transition cannot run against it
 * without JS or ::details-content, and neither is worth losing the no-JS
 * guarantee for. The chevron, the rule and the row tint animate instead — and
 * all of them stand down under prefers-reduced-motion.
 */

/** How many entries render expanded. Enough to make the section read as answered
 *  content on arrival, few enough that the list stays scannable. */
const OPEN_BY_DEFAULT = 3

export function FaqSection({
  items,
  title = "Frequently asked questions",
  id = "faq",
}: {
  items: FaqItem[]
  title?: string
  id?: string
}) {
  if (!items?.length) return null
  return (
    <section id={id} className="relative overflow-hidden border-t bg-background">
      {/* Ambient field. Two very low-alpha radials in the brand accents give the
          section depth without becoming a coloured panel, and a hairline along
          the top edge fades in from both sides. Purely decorative, so aria-hidden
          and pointer-events-none. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(60rem 30rem at 12% -10%, color-mix(in oklab, var(--mt-teal) 9%, transparent), transparent 70%)," +
            "radial-gradient(50rem 26rem at 100% 110%, color-mix(in oklab, var(--mt-violet) 8%, transparent), transparent 70%)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px"
        style={{
          background:
            "linear-gradient(to right, transparent, color-mix(in oklab, var(--mt-teal) 55%, transparent), transparent)",
        }}
      />

      <div className="relative mx-auto max-w-6xl px-5 py-20 sm:px-6 lg:px-8 lg:py-28">
        <div className="grid gap-12 lg:grid-cols-[minmax(0,19rem)_1fr] lg:gap-16">
          {/* Left rail — sticks while the answers scroll past it on desktop. */}
          <div className="min-w-0 lg:sticky lg:top-24 lg:self-start">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.28em]"
              style={{ color: "var(--mt-teal-ink)" }}
            >
              FAQ
            </p>
            <h2 className="mt-4 text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
              {title}
            </h2>
            <div
              aria-hidden
              className="mt-6 h-px w-16"
              style={{
                background:
                  "linear-gradient(to right, var(--mt-teal), color-mix(in oklab, var(--mt-teal) 0%, transparent))",
              }}
            />
            <p className="mt-6 font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              {items.length.toString().padStart(2, "0")} entries
            </p>
          </div>

          {/* The list, as an overlapping deck of cards rather than hairline rows.
              `relative` so each card's z-index is resolved against this stack and
              not against whatever ancestor happens to be positioned. */}
          <div className="relative min-w-0">
            {items.map((item, i) => (
              // The first few open by default: a collapsed <details> still ships its
              // answer in the server HTML, but an open one is unambiguously visible
              // content rather than something a reader (or an extractor) must act to
              // reveal. The questions are the only question-shaped strings on the
              // site, so they are wrapped in <h3> to enter the document outline —
              // <summary> alone carries no heading semantics.
              <details
                key={i}
                open={i < OPEN_BY_DEFAULT}
                /* A vertical deck: each card's top edge tucks under the previous
                   card's bottom, like a stack of papers.

                   z-index DESCENDS with position, so earlier cards sit on top.
                   That direction matters more here than on the hero row. These
                   entries expand, and an open answer has to be able to extend
                   over what follows it — with the stacking reversed, the next
                   card would cover the bottom of the answer you just opened.

                   The overlap is a constant negative margin, so it stays 12px at
                   the card boundary no matter how tall an open answer grows: the
                   following card is pushed down by normal flow along with it. No
                   question is ever hidden behind the card above it. */
                style={{ zIndex: items.length - i }}
                className="group relative -mt-3 rounded-xl border bg-card shadow-sm transition-shadow duration-300 first:mt-0 hover:shadow-md open:shadow-lg motion-reduce:transition-none"
              >
                {/* The rule that ignites. Sits flush to the left edge and scales
                    up from nothing when the entry opens, which is the one moment
                    of motion the native disclosure actually gives us. */}
                <span
                  aria-hidden
                  className="pointer-events-none absolute bottom-0 left-0 top-0 w-[3px] origin-top scale-y-0 rounded-l-xl transition-transform duration-300 group-open:scale-y-100 motion-reduce:transition-none"
                  style={{ backgroundColor: "var(--mt-teal)" }}
                />

                <summary
                  className="flex cursor-pointer list-none items-start gap-4 rounded-xl py-5 pl-6 pr-4 transition-colors hover:bg-muted/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring motion-reduce:transition-none marker:hidden [&::-webkit-details-marker]:hidden"
                >
                  <span
                    className="mt-0.5 shrink-0 font-mono text-[11px] font-bold tabular-nums tracking-widest transition-colors motion-reduce:transition-none"
                    style={{ color: "var(--mt-teal-ink)" }}
                    aria-hidden
                  >
                    {(i + 1).toString().padStart(2, "0")}
                  </span>
                  <h3 className="min-w-0 flex-1 text-base font-semibold tracking-tight text-foreground sm:text-lg">
                    {item.q}
                  </h3>
                  {/* A plus that rotates into a cross — clearer at a glance than a
                      chevron about whether a row is open. (45deg, so it lands on
                      an x rather than a minus; a minus would need a second glyph
                      and this reads as "close this" either way.) */}
                  <Plus
                    className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-300 group-open:rotate-45 motion-reduce:transition-none"
                    aria-hidden
                  />
                </summary>

                <div className="pb-6 pl-[4.1rem] pr-6">
                  <p className="text-[15px] leading-relaxed text-muted-foreground">{item.a}</p>
                </div>
              </details>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

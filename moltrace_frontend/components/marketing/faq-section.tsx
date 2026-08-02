import { ChevronDown } from "lucide-react"

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
    <section id={id} className="border-t bg-muted/20">
      <div className="mx-auto max-w-3xl px-5 py-16 sm:px-6 lg:px-8 lg:py-20">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-teal-ink)" }}
        >
          FAQ
        </p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h2>
        <div className="mt-8 divide-y rounded-2xl border bg-card">
          {items.map((item, i) => (
            // The first few open by default: a collapsed <details> still ships its
            // answer in the server HTML, but an open one is unambiguously visible
            // content rather than something a reader (or an extractor) must act to
            // reveal. The questions are the only question-shaped strings on the
            // site, so they are wrapped in <h3> to enter the document outline —
            // <summary> alone carries no heading semantics.
            <details key={i} open={i < OPEN_BY_DEFAULT} className="group px-5 py-4 sm:px-6">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-left marker:hidden [&::-webkit-details-marker]:hidden">
                <h3 className="text-base font-semibold tracking-tight text-foreground">
                  {item.q}
                </h3>
                <ChevronDown
                  className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
                  aria-hidden
                />
              </summary>
              <p className="mt-3 text-base leading-relaxed text-muted-foreground">{item.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
}

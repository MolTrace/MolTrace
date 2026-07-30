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
            <details key={i} className="group px-5 py-4 sm:px-6">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-left text-base font-semibold tracking-tight text-foreground marker:hidden [&::-webkit-details-marker]:hidden">
                {item.q}
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

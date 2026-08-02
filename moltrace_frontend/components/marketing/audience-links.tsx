import Link from "next/link"
import { ArrowRight } from "lucide-react"

/**
 * Contextual links from a module page to the audience pages it serves.
 *
 * WHY THIS EXISTS: the internal link graph ran one way. Every persona page
 * linked out to the module pages, but no module page linked back, so
 * /academic-research, /cro-analytical and /regulatory-affairs had zero in-body
 * inbound links across the whole site — reachable only through the header
 * dropdown. In-body links from an established page are the lever the indexing
 * runbook names for a URL stuck at "Discovered - currently not indexed", and
 * these three had none.
 *
 * WHICH AUDIENCES: each module lists exactly the personas whose own page links
 * TO it, so the graph reciprocates rather than asserting a new claim about who
 * a module is for. /academic-research does not link to Regentry (academic labs
 * are not filing submissions), so Regentry does not list it back.
 */
export type Audience = {
  href: string
  label: string
}

export const AUDIENCES: Record<string, Audience> = {
  pharma: { href: "/pharmaceutical-rd", label: "Pharmaceutical R&D" },
  academic: { href: "/academic-research", label: "Academic research" },
  cro: { href: "/cro-analytical", label: "CRO & analytical labs" },
  regulatory: { href: "/regulatory-affairs", label: "Regulatory affairs" },
}

export function AudienceLinks({
  audiences,
  moduleName,
}: {
  audiences: Audience[]
  moduleName: string
}) {
  if (!audiences.length) return null
  return (
    <section className="border-t">
      <div className="mx-auto max-w-5xl px-5 py-12 sm:px-6 lg:px-8">
        <h2 className="text-center text-sm font-semibold tracking-tight text-muted-foreground">
          Who uses {moduleName}
        </h2>
        <ul className="mt-5 flex flex-wrap items-center justify-center gap-3">
          {audiences.map((audience) => (
            <li key={audience.href}>
              <Link
                href={audience.href}
                className="inline-flex items-center gap-1.5 rounded-full border px-4 py-2 text-sm text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground"
              >
                {audience.label}
                <ArrowRight className="h-3 w-3" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

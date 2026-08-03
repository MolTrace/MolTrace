import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ArrowRight, Eye } from "lucide-react"
import Link from "next/link"
import { HeroMoleculeLayer } from "./hero-molecule-layer"

export function Hero() {
  return (
    <section className="hero-compat-surface relative overflow-hidden bg-background text-foreground">
      <HeroMoleculeLayer />
      <div className="hero-compat-overlay pointer-events-none absolute inset-0 z-[5]" aria-hidden />
      <div className="relative z-10 mx-auto max-w-7xl px-4 py-24 sm:px-6 sm:py-32 lg:px-8 lg:py-40">
        <div className="mx-auto max-w-4xl text-center">
          <Badge variant="outline" className="mb-6 px-4 py-1.5 text-sm font-medium">
            Evidence-first AI for regulated pharma &amp; chemical R&amp;D
          </Badge>
          <h1 className="hero-copy-wrap text-balance text-4xl font-semibold tracking-tight sm:text-5xl lg:text-6xl">
            Analytical evidence you can trace under audit.
          </h1>
          <p className="hero-copy-wrap mx-auto mt-6 max-w-2xl text-pretty text-lg text-muted-foreground sm:text-xl">
            MolTrace turns raw NMR and LC-MS data into verified structures, ICH-aligned
            regulatory deliverables, and optimized reactions &mdash; every result backed by
            calibrated confidence scores, citations, and a tamper-evident audit trail.
          </p>
          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Button size="lg" className="min-w-[180px] gap-2" asChild>
              <Link href="/contact?reason=Request%20a%20demo">
                Request Demo
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button variant="outline" size="lg" className="min-w-[180px] gap-2" asChild>
              <Link href="#solutions">
                <Eye className="h-4 w-4" />
                See how evidence works
              </Link>
            </Button>
          </div>
        </div>

        {/* Stats bar */}
        <div className="hero-stat-grid mx-auto mt-20 grid max-w-4xl grid-cols-2 gap-8 border-t pt-10 sm:grid-cols-4">
          {[
            { value: "SpectraCheck", label: "Raw spectra → structure evidence" },
            { value: "Regentry", label: "Evidence → ICH action items" },
            { value: "Repho", label: "Constraints → optimized reactions" },
            { value: "Report", label: "Audit-ready dossier & human sign-off" },
          ].map((stat) => (
            <div key={stat.label} className="text-center">
              <div className="text-3xl font-semibold tracking-tight">{stat.value}</div>
              <div className="mt-1 text-sm text-muted-foreground">{stat.label}</div>
            </div>
          ))}
        </div>
        <p className="mt-8 text-center font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
          Designed to support 21 CFR Part 11 &middot; EU Annex 11 &middot; ICH Q-Series &middot; GxP / GAMP 5
        </p>
      </div>
    </section>
  )
}

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ArrowRight, Play } from "lucide-react"
import Link from "next/link"
import { HeroMoleculeLayer } from "./hero-molecule-layer"

export function Hero() {
  return (
    <section className="hero-compat-surface relative overflow-hidden bg-background text-foreground">
      <div className="scientific-grid-subtle absolute inset-0 z-0" aria-hidden />
      <HeroMoleculeLayer />
      <div className="hero-compat-overlay pointer-events-none absolute inset-0 z-[5]" aria-hidden />
      <div className="relative z-10 mx-auto max-w-7xl px-4 py-24 sm:px-6 sm:py-32 lg:px-8 lg:py-40">
        <div className="mx-auto max-w-4xl text-center">
          <Badge variant="outline" className="mb-6 px-4 py-1.5 text-sm font-medium">
            Trusted by 50+ pharmaceutical R&D teams
          </Badge>
          <h1 className="hero-copy-wrap text-balance text-4xl font-semibold tracking-tight sm:text-5xl lg:text-6xl">
            The Unified Intelligence Platform for Chemical and Pharmaceutical R&D.
          </h1>
          <p className="hero-copy-wrap mx-auto mt-6 max-w-2xl text-pretty text-lg text-muted-foreground sm:text-xl">
            Accelerate discovery from raw spectral data to compliant, optimized reactions with MolTrace&apos;s hybrid AI
            architecture.
          </p>
          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Button size="lg" className="min-w-[180px] gap-2" asChild>
              <Link href="#demo">
                Request Demo
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button variant="outline" size="lg" className="min-w-[180px] gap-2" asChild>
              <Link href="/dashboard">
                <Play className="h-4 w-4" />
                View Platform
              </Link>
            </Button>
          </div>
        </div>

        {/* Stats bar */}
        <div className="hero-stat-grid mx-auto mt-20 grid max-w-4xl grid-cols-2 gap-8 border-t pt-10 sm:grid-cols-4">
          {[
            { value: "94%", label: "Structure elucidation accuracy" },
            { value: "12x", label: "Faster than manual analysis" },
            { value: "500+", label: "Regulatory submissions supported" },
            { value: "99.9%", label: "Uptime SLA" },
          ].map((stat) => (
            <div key={stat.label} className="text-center">
              <div className="text-3xl font-semibold tracking-tight">{stat.value}</div>
              <div className="mt-1 text-sm text-muted-foreground">{stat.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

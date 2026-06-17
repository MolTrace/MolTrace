"use client"

import Link from "next/link"
import { ArrowRight, FlaskConical, GitBranch, ShieldCheck } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  GsdReadinessVerdictCard,
  GsdTelemetryPanel,
} from "@/components/spectracheck/gsd-telemetry-panel"

/**
 * Admin GSD readiness workspace — verdict-driven action surface.
 *
 * Phase 25c: replaces the prior informational banner with the focused
 * three-variant action card (NeedMoreData / ReadyToFlip / Blocked) the
 * handoff packet specified. The telemetry panel below provides the
 * drill-in numbers behind whichever verdict is active.
 */

export function GsdReadinessWorkspace() {
  return (
    <div className="space-y-8 p-6">
      {/* Header */}
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-teal-ink)" }}
          >
            Admin · GSD readiness
          </p>
          <Badge
            variant="outline"
            className="border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300"
          >
            <FlaskConical className="mr-1 h-3 w-3" aria-hidden />
            Experimental backend
          </Badge>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          GSD-Prompt-3 promotion gate · ready to flip?
        </h1>
        <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">
          One screen. One verdict. One action. The card below switches its shape based on the
          backend-owned <code className="font-mono">flip_readiness_verdict</code>, so this page
          tells you the next step without any FE re-derivation. Policy thresholds shown are the
          live snapshot from the same response — backend tightens the policy, FE updates
          automatically.
        </p>
      </header>

      {/* Verdict-driven action card — the single source of "what to do next" */}
      <GsdReadinessVerdictCard testId="gsd-admin-verdict" />

      {/* Telemetry panel — drill-in numbers behind the verdict */}
      <GsdTelemetryPanel mode="admin" testId="gsd-readiness-telemetry-panel" />

      {/* Cross-references */}
      <section className="grid gap-3 rounded-2xl border bg-muted/20 p-5 sm:grid-cols-2 sm:items-center">
        <div className="space-y-1">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
            Cross-references
          </p>
          <p className="text-sm leading-relaxed text-foreground">
            The verdict logic, the policy thresholds, and the corpus-level Δ numbers all live in
            the technical paper. The CI gate that guards detector drift is wired to the FE-produced
            A/B JSON.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild variant="outline" size="sm" className="gap-1.5">
            <Link
              href="https://docs.moltrace.co/guides/resources/white-papers/"
              target="_blank"
              rel="noopener noreferrer"
            >
              <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
              Technical paper §3.1
              <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </Link>
          </Button>
          <Button asChild variant="outline" size="sm" className="gap-1.5">
            <Link href="/blog">
              <GitBranch className="h-3.5 w-3.5" aria-hidden />
              Field notes
              <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </Link>
          </Button>
        </div>
      </section>
    </div>
  )
}

"use client"

import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  AlertTriangle,
  BookMarked,
  ClipboardCheck,
  Download,
  FileOutput,
  Globe,
  Gavel,
  Lock,
  Shield,
  UserRound,
} from "lucide-react"

/** Static demo rows — not synced to any backend. */
const DEMO_DOSSIER = {
  project: "PRJ-MTX-2047",
  compound: "MTX-447",
  salt_form: "mesylate",
  development_stage: "Phase-compatible CMC draft",
  dossier_version: "0.4-demo",
  last_updated: "2026-05-01",
} as const

const DEMO_JURISDICTIONS = [
  { id: "fda", label: "United States (FDA / CDER)", hint: "Demo selector — no filing logic" },
  { id: "ema", label: "EU (EMA)", hint: "Demo selector" },
  { id: "pmda", label: "Japan (PMDA)", hint: "Demo selector" },
  { id: "multi", label: "Multi-region (placeholder)", hint: "Demo selector" },
] as const

const DEMO_REQUIREMENTS = [
  {
    id: "r1",
    label: "Identity & structure proof (spectral concordance)",
    framework: "ICH Q6A concept",
    status: "complete" as const,
    evidence_refs: ["DOSS-§2.3.1", "NMR-REP-014"],
  },
  {
    id: "r2",
    label: "Organic impurity thresholds & analytical justification",
    framework: "ICH Q3A / Q3B",
    status: "in_progress" as const,
    evidence_refs: ["HPLC-VAL-009"],
  },
  {
    id: "r3",
    label: "Residual solvents",
    framework: "ICH Q3C",
    status: "pending" as const,
    evidence_refs: [],
  },
  {
    id: "r4",
    label: "Genotoxic impurity risk narrative",
    framework: "ICH M7",
    status: "pending" as const,
    evidence_refs: [],
  },
] as const

/**
 * AI-style excerpts MUST carry citation placeholders + human review state.
 * Copy explicitly avoids presenting guidance as final or regulator-ready.
 */
const DEMO_CITED_EVIDENCE_CARDS = [
  {
    id: "ai-1",
    title: "Draft narrative fragment (demo)",
    excerpt:
      "Impurity profile discussion should reference validated chromatographic methods and bracketed batch data…",
    citations: [
      { ref: "[PLACEHOLDER] Internal method validation summary · DOC-ID pending", type: "document" },
      { ref: "ICH Q3B(R2) — bracketing principles (retrieve exact clause in regulated workflow)", type: "guidance" },
    ],
    human_review_state: "pending_review" as const,
    citation_coverage: "partial" as const,
    disclaimer:
      "Illustrative wording only. Replace bracketed references with controlled artefacts before any submission use.",
  },
  {
    id: "ai-2",
    title: "Risk-oriented checklist suggestion (demo)",
    excerpt:
      "Consider documenting purge rationale for potentially genotoxic intermediates when carry-through exceeds…",
    citations: [
      { ref: "[PLACEHOLDER] Route assessment worksheet · not attached in demo shell", type: "document" },
      { ref: "ICH M7 — allowable intake concepts (confirm numeric limits against internal tox)", type: "guidance" },
    ],
    human_review_state: "needs_additional_source" as const,
    citation_coverage: "insufficient" as const,
    disclaimer:
      "Uncited numeric thresholds must not be copied into filings — supply tox references and internal limits.",
  },
] as const

const DEMO_RISK = {
  summary: "Elevated documentation gap (demo label)",
  level: "medium" as const,
  drivers: [
    "Two checklist items lack linked evidence artefacts in this demo dataset.",
    "One AI excerpt flagged as needing additional sources before human sign-off.",
  ],
}

export function RegulatoryHubWorkspace() {
  const [jurisdiction, setJurisdiction] = useState<string>(DEMO_JURISDICTIONS[0].id)
  const [reviewerNotes, setReviewerNotes] = useState(
    "Demo scratchpad — notes are local-only until persistence API exists.",
  )

  return (
    <div className="mx-auto max-w-[1200px] space-y-8 pb-12">
      <header className="space-y-4 border-b pb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="font-mono text-xs">
                Regulatory Hub
              </Badge>
              <Badge
                variant="secondary"
                className="gap-1 border-dashed border-warning/60 bg-warning/10 text-warning-foreground"
              >
                <AlertTriangle className="h-3 w-3" />
                Demo data — not linked to eCTD / vault
              </Badge>
            </div>
            <h1 className="text-2xl font-semibold tracking-tight">Submission readiness workspace</h1>
            <p className="max-w-3xl text-muted-foreground">
              Track dossier context, jurisdictional assumptions, and evidence-backed requirements. AI-assisted text is
              shown only with explicit citations and human review states — never as final regulatory guidance in this
              shell.
            </p>
          </div>
          <Button variant="outline" size="sm" disabled className="gap-2">
            <Lock className="h-4 w-4" />
            Connect vault (disabled)
          </Button>
        </div>

        <Card className="border-primary/30 bg-primary/[0.04]">
          <CardContent className="flex flex-wrap gap-3 py-4 text-sm leading-relaxed">
            <Shield className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
            <div className="min-w-0 space-y-1">
              <p className="font-medium text-foreground">Citation &amp; review policy (UI shell)</p>
              <p className="text-muted-foreground">
                Any regulatory-style or AI-generated excerpt must display source placeholders or document IDs. Outputs
                carry a <strong>human review state</strong> (e.g. pending, needs sources).{" "}
                <span className="text-foreground">
                  Uncited text cannot be presented here as final or regulator-ready guidance.
                </span>
              </p>
            </div>
          </CardContent>
        </Card>
      </header>

      {/* Project / compound dossier */}
      <section aria-labelledby="dossier-heading">
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <BookMarked className="h-5 w-5 text-muted-foreground" aria-hidden />
              <CardTitle id="dossier-heading" className="text-lg">
                Project / compound dossier
              </CardTitle>
            </div>
            <CardDescription>High-level identifiers — demo snapshot for layout only.</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div className="rounded-md border bg-muted/30 px-4 py-3">
                <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Project</dt>
                <dd className="mt-1 font-mono text-sm font-semibold">{DEMO_DOSSIER.project}</dd>
              </div>
              <div className="rounded-md border bg-muted/30 px-4 py-3">
                <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Compound</dt>
                <dd className="mt-1 font-mono text-sm font-semibold">{DEMO_DOSSIER.compound}</dd>
              </div>
              <div className="rounded-md border bg-muted/30 px-4 py-3">
                <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Salt / form</dt>
                <dd className="mt-1 text-sm">{DEMO_DOSSIER.salt_form}</dd>
              </div>
              <div className="rounded-md border bg-muted/30 px-4 py-3 sm:col-span-2 lg:col-span-2">
                <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Stage</dt>
                <dd className="mt-1 text-sm">{DEMO_DOSSIER.development_stage}</dd>
              </div>
              <div className="rounded-md border bg-muted/30 px-4 py-3">
                <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Dossier version</dt>
                <dd className="mt-1 font-mono text-sm">{DEMO_DOSSIER.dossier_version}</dd>
              </div>
              <div className="rounded-md border bg-muted/30 px-4 py-3">
                <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Snapshot date</dt>
                <dd className="mt-1 font-mono text-sm">{DEMO_DOSSIER.last_updated}</dd>
              </div>
            </dl>
          </CardContent>
        </Card>
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Jurisdiction */}
        <section className="lg:col-span-1" aria-labelledby="jurisdiction-heading">
          <Card className="h-full">
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <Globe className="h-5 w-5 text-muted-foreground" aria-hidden />
                <CardTitle id="jurisdiction-heading" className="text-base">
                  Jurisdiction
                </CardTitle>
              </div>
              <CardDescription>Select target regulator context (demo — does not change backend rules).</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Label htmlFor="jurisdiction-select" className="text-xs text-muted-foreground">
                Active jurisdiction (placeholder)
              </Label>
              <Select value={jurisdiction} onValueChange={setJurisdiction}>
                <SelectTrigger id="jurisdiction-select" className="w-full">
                  <SelectValue placeholder="Choose region" />
                </SelectTrigger>
                <SelectContent>
                  {DEMO_JURISDICTIONS.map((j) => (
                    <SelectItem key={j.id} value={j.id}>
                      {j.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {DEMO_JURISDICTIONS.find((j) => j.id === jurisdiction)?.hint}
              </p>
            </CardContent>
          </Card>
        </section>

        {/* Risk status */}
        <section className="lg:col-span-2" aria-labelledby="risk-heading">
          <Card className="h-full border-warning/40">
            <CardHeader className="pb-3">
              <div className="flex flex-wrap items-center gap-2">
                <Gavel className="h-5 w-5 text-warning" aria-hidden />
                <CardTitle id="risk-heading" className="text-base">
                  Risk status
                </CardTitle>
                <Badge variant="outline" className="border-warning/60 bg-warning/10 text-warning-foreground">
                  Demo assessment
                </Badge>
              </div>
              <CardDescription>Illustrative readiness gaps — not a formal risk register.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-sm font-medium">{DEMO_RISK.summary}</span>
                <Badge variant="secondary">Level: {DEMO_RISK.level}</Badge>
              </div>
              <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                {DEMO_RISK.drivers.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </section>
      </div>

      {/* Requirement checklist */}
      <section aria-labelledby="requirements-heading">
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <ClipboardCheck className="h-5 w-5 text-muted-foreground" aria-hidden />
              <CardTitle id="requirements-heading" className="text-lg">
                Requirement checklist
              </CardTitle>
            </div>
            <CardDescription>
              Framework-aligned items with linked evidence handles (demo). Checkboxes are visual only in this shell.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[52px]" />
                  <TableHead>Requirement</TableHead>
                  <TableHead>Framework</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Evidence refs</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {DEMO_REQUIREMENTS.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell>
                      <Checkbox checked={row.status === "complete"} disabled aria-readonly />
                    </TableCell>
                    <TableCell className="max-w-[320px] font-medium">{row.label}</TableCell>
                    <TableCell className="text-muted-foreground">{row.framework}</TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          row.status === "complete"
                            ? "default"
                            : row.status === "in_progress"
                              ? "secondary"
                              : "outline"
                        }
                        className="capitalize"
                      >
                        {row.status.replace("_", " ")}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {row.evidence_refs.length ? row.evidence_refs.join(" · ") : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </section>

      {/* Cited evidence cards (AI excerpts with mandatory citations + review state) */}
      <section aria-labelledby="evidence-ai-heading" className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 id="evidence-ai-heading" className="text-lg font-semibold tracking-tight">
              Regulatory AI excerpts (citation-required)
            </h2>
            <p className="text-sm text-muted-foreground">
              Each card lists sources or explicit placeholders. Review state must reach approved before any excerpt could
              feed export pipelines.
            </p>
          </div>
          <Badge variant="outline" className="shrink-0 font-normal">
            Not final guidance
          </Badge>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {DEMO_CITED_EVIDENCE_CARDS.map((card) => (
            <Card key={card.id} className="flex flex-col border-muted">
              <CardHeader className="pb-2">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <CardTitle className="text-base leading-snug">{card.title}</CardTitle>
                  <HumanReviewBadge state={card.human_review_state} coverage={card.citation_coverage} />
                </div>
                <CardDescription className="text-xs">{card.disclaimer}</CardDescription>
              </CardHeader>
              <CardContent className="mt-auto flex flex-1 flex-col gap-4">
                <blockquote className="rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm leading-relaxed text-foreground">
                  {card.excerpt}
                </blockquote>
                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Citations &amp; sources
                  </p>
                  <ul className="space-y-2">
                    {card.citations.map((c, i) => (
                      <li
                        key={`${card.id}-cit-${i}`}
                        className="flex gap-2 rounded-md border bg-card px-2 py-2 text-xs leading-snug"
                      >
                        <Badge variant="outline" className="shrink-0 font-mono capitalize">
                          {c.type}
                        </Badge>
                        <span className="text-muted-foreground">{c.ref}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <p className="text-xs text-muted-foreground">
                  This excerpt is <strong>not</strong> submission-ready. Confirm against controlled documents and
                  qualified reviewer sign-off.
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Reviewer notes */}
      <section aria-labelledby="notes-heading">
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <UserRound className="h-5 w-5 text-muted-foreground" aria-hidden />
              <CardTitle id="notes-heading" className="text-lg">
                Reviewer notes
              </CardTitle>
            </div>
            <CardDescription>
              Local-only draft — no sync. Replace with authenticated review service when API exists.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea
              value={reviewerNotes}
              onChange={(e) => setReviewerNotes(e.target.value)}
              rows={5}
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              Typed content is browser-local for demo purposes and will not persist after refresh.
            </p>
          </CardContent>
        </Card>
      </section>

      {/* Report export controls */}
      <section aria-labelledby="export-heading">
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <FileOutput className="h-5 w-5 text-muted-foreground" aria-hidden />
              <CardTitle id="export-heading" className="text-lg">
                Report export controls
              </CardTitle>
            </div>
            <CardDescription>
              Bundling requires validated artefacts and reviewer workflow — controls remain disabled without backend.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-3">
              <Button disabled className="gap-2">
                <Download className="h-4 w-4" />
                Export briefing (PDF)
              </Button>
              <Button variant="outline" disabled className="gap-2">
                <Download className="h-4 w-4" />
                Export evidence index (JSON)
              </Button>
              <Button variant="outline" disabled className="gap-2">
                <Download className="h-4 w-4" />
                eCTD stub (disabled)
              </Button>
            </div>
            <Separator />
            <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
              <Checkbox id="export-gate" disabled />
              <Label htmlFor="export-gate" className="font-normal leading-snug">
                I confirm cited sources are attached and human review is complete (demo checkbox — non-functional).
              </Label>
            </div>
          </CardContent>
        </Card>
      </section>

      <Card className="border-dashed bg-muted/30">
        <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4 text-xs text-muted-foreground">
          <span>MolTrace Regulatory Hub · UI scaffold · no regulatory AI inference executed</span>
          <Badge variant="outline" className="font-normal">
            Citations + human review required for any production export
          </Badge>
        </CardContent>
      </Card>
    </div>
  )
}

function HumanReviewBadge({
  state,
  coverage,
}: {
  state: "pending_review" | "needs_additional_source"
  coverage: "partial" | "insufficient"
}) {
  const label =
    state === "pending_review"
      ? "Human review: pending"
      : state === "needs_additional_source"
        ? "Human review: needs sources"
        : "Human review"
  return (
    <div className="flex flex-wrap gap-1">
      <Badge variant="secondary" className="gap-1">
        <Shield className="h-3 w-3" />
        {label}
      </Badge>
      <Badge variant="outline" className="font-mono text-[10px] uppercase">
        Citations: {coverage}
      </Badge>
    </div>
  )
}

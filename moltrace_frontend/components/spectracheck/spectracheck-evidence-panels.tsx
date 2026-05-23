"use client"

/**
 * Display panels for the enriched analyze response.
 *
 * The backend `/nmr/processed/analyze` endpoint returns peaks enriched with
 * `category`, `chemical_region`, `labile_hint`, `impurity_match`, and
 * `category_reason` plus top-level `impurity_candidates`,
 * `labile_hydrogen_summary`, `peak_category_summary`, and
 * `predicted_vs_observed`. These components surface that data so users can
 * trace *why* each peak was categorized — the explainability angle.
 *
 * All components accept loose payloads and silently render nothing when their
 * data is missing or malformed, so they can be dropped into any results panel
 * without crashing on legacy responses.
 */

import { memo, useMemo } from "react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ModuleCard } from "@/components/dashboard/module-card"
import {
  AlertTriangle,
  Beaker,
  BookOpen,
  FileText,
  ListChecks,
  Sparkles,
  Tag,
  Target,
} from "lucide-react"
import { isRecord } from "@/components/spectracheck/spectracheck-nmr-result-parse"

type RawPeak = Record<string, unknown>

/**
 * Color cues for peak categories. Keep the palette small so the picked-peaks
 * table reads as a single-glance grouping.
 */
const CATEGORY_STYLE: Record<string, { color: string; bg: string }> = {
  aromatic_alkene: { color: "var(--mt-teal)", bg: "var(--mt-teal-soft)" },
  // ``olefinic`` is now only assigned when the SMILES actually has olefinic
  // (non-aromatic C=C) protons — see peak_categorization._classify_anomeric_vs_olefinic.
  olefinic: { color: "var(--mt-teal)", bg: "var(--mt-teal-soft)" },
  aldehyde: { color: "var(--mt-amber)", bg: "rgba(231, 165, 67, 0.12)" },
  carbonyl: { color: "var(--mt-amber)", bg: "rgba(231, 165, 67, 0.12)" },
  carboxylic_acid: { color: "var(--mt-amber)", bg: "rgba(231, 165, 67, 0.12)" },
  labile_OH_NH_SH: { color: "var(--mt-amber)", bg: "rgba(231, 165, 67, 0.12)" },
  oxygenated: { color: "var(--mt-blue, #4c6fae)", bg: "rgba(76, 111, 174, 0.12)" },
  nitrogen_adjacent: { color: "var(--mt-blue, #4c6fae)", bg: "rgba(76, 111, 174, 0.12)" },
  anomeric: { color: "var(--mt-blue, #4c6fae)", bg: "rgba(76, 111, 174, 0.12)" },
  // Distinct purple for the ambiguous bucket so reviewers know the
  // categoriser couldn't disambiguate (no SMILES, or both motifs present).
  anomeric_or_olefinic: { color: "#9333EA", bg: "rgba(147, 51, 234, 0.12)" },
  aliphatic: { color: "var(--mt-green)", bg: "var(--mt-green-soft)" },
  solvent: { color: "var(--mt-muted, #888)", bg: "rgba(128, 128, 128, 0.08)" },
  impurity: { color: "var(--mt-red, #b8474a)", bg: "rgba(184, 71, 74, 0.12)" },
  unknown: { color: "var(--mt-muted, #888)", bg: "rgba(128, 128, 128, 0.08)" },
}

function categoryStyle(category: string | null | undefined) {
  if (!category) return CATEGORY_STYLE.unknown
  return CATEGORY_STYLE[category] ?? CATEGORY_STYLE.unknown
}

function humanizeCategory(category: string | null | undefined): string {
  if (!category) return "—"
  if (category === "anomeric_or_olefinic") return "Anomeric / olefinic (ambiguous)"
  return category
    .replace(/_/g, " ")
    .replace("OH NH SH", "OH / NH / SH")
    .replace(/^\w/, (c) => c.toUpperCase())
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null
}

function extractRawPeaks(payload: unknown): RawPeak[] {
  if (!isRecord(payload)) return []
  const peaks = payload.peaks
  if (!Array.isArray(peaks)) return []
  return peaks.filter((p): p is RawPeak => isRecord(p))
}

// ────────────────────────────────────────────────────────────────────────────
// Picked peaks — enriched
// ────────────────────────────────────────────────────────────────────────────

function EnrichedPickedPeaksPanelImpl({
  payload,
  fallbackTitle = "Picked peaks",
}: {
  payload: unknown
  fallbackTitle?: string
}) {
  const peaks = useMemo(() => extractRawPeaks(payload), [payload])
  if (peaks.length === 0) {
    return null
  }
  const hasEnrichment = peaks.some((p) => "category" in p)
  const visible = peaks.slice(0, 200)
  return (
    <Card
      className="overflow-hidden rounded-xl py-0"
      style={{ borderTop: "3px solid var(--mt-teal)" }}
      data-testid="enriched-picked-peaks"
    >
      <CardContent className="space-y-2 py-3">
        <div className="flex items-center justify-between">
          <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
            <ListChecks className="h-3 w-3" aria-hidden />
            {fallbackTitle}
          </p>
          <span className="font-mono text-[10px] text-muted-foreground">
            {peaks.length > 200 ? `${peaks.length} (showing 200)` : peaks.length}
          </span>
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-[10px] uppercase tracking-wide">δ (ppm)</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wide">Mult</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wide">∫ H</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wide">J (Hz)</TableHead>
                {hasEnrichment ? (
                  <>
                    <TableHead className="text-[10px] uppercase tracking-wide">Category</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wide">Region</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wide">Impurity</TableHead>
                  </>
                ) : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((peak, idx) => {
                const shift = asNumber(peak.shift_ppm)
                const multiplicity = asString(peak.multiplicity)
                const integration = asNumber(peak.integration_h)
                const j = Array.isArray(peak.j_values_hz)
                  ? (peak.j_values_hz as unknown[])
                      .filter((v): v is number => typeof v === "number" && Number.isFinite(v))
                      .map((v) => v.toFixed(1))
                      .join(", ")
                  : ""
                const category = asString(peak.category)
                const region = asString(peak.chemical_region)
                const impurity = isRecord(peak.impurity_match)
                  ? (asString(peak.impurity_match.label) ?? null)
                  : null
                const labile = peak.labile_hint === true
                const reason = asString(peak.category_reason)
                const style = categoryStyle(category)
                return (
                  <TableRow key={idx} data-testid="enriched-peak-row">
                    <TableCell className="font-mono text-xs">{shift !== null ? shift.toFixed(3) : "—"}</TableCell>
                    <TableCell className="font-mono text-xs">{multiplicity ?? "—"}</TableCell>
                    <TableCell className="font-mono text-xs">
                      {integration !== null ? integration.toFixed(2) : "—"}
                    </TableCell>
                    <TableCell className="font-mono text-[10px]">{j || "—"}</TableCell>
                    {hasEnrichment ? (
                      <>
                        <TableCell>
                          {category ? (
                            <Badge
                              variant="outline"
                              className="font-mono text-[10px]"
                              style={{ borderColor: style.color, backgroundColor: style.bg, color: style.color }}
                              title={reason ?? undefined}
                            >
                              {humanizeCategory(category)}
                              {labile ? " · labile" : ""}
                            </Badge>
                          ) : (
                            "—"
                          )}
                        </TableCell>
                        <TableCell className="text-[11px] text-muted-foreground" title={reason ?? undefined}>
                          {region ?? "—"}
                        </TableCell>
                        <TableCell className="text-[11px]" style={{ color: impurity ? "var(--mt-red, #b8474a)" : undefined }}>
                          {impurity ?? "—"}
                        </TableCell>
                      </>
                    ) : null}
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Inferred NMR text — the backend-generated prose summary
// ────────────────────────────────────────────────────────────────────────────

/**
 * Read the backend-generated NMR string from a loose payload.
 *
 * The processed-spectrum analyze endpoint puts the inferred multiplet summary
 * — e.g. ``"5.23 (d, J = 3.6 Hz, 12.5H), 3.95 (ddd, J = 10.3, 4.6, 2.6 Hz, 9.5H)"``
 * — on ``preview.inferred_nmr_text`` and ``analysis.inferred_nmr_text``. The
 * panel accepts either the preview or the analysis payload directly, and also
 * the legacy shape where the field sits at the top of the object.
 */
function readInferredNmrText(payload: unknown): string | null {
  if (!isRecord(payload)) return null
  const direct = payload.inferred_nmr_text
  if (typeof direct === "string" && direct.trim().length > 0) {
    return direct.trim()
  }
  // Some callers hand us the wrapper object that holds the preview and the
  // analysis blocks side-by-side; reach in and prefer the analysis text.
  const analysis = isRecord(payload.analysis) ? payload.analysis.inferred_nmr_text : null
  if (typeof analysis === "string" && analysis.trim().length > 0) {
    return analysis.trim()
  }
  const preview = isRecord(payload.preview) ? payload.preview.inferred_nmr_text : null
  if (typeof preview === "string" && preview.trim().length > 0) {
    return preview.trim()
  }
  return null
}

function InferredNmrTextPanelImpl({
  payload,
  title = "Inferred NMR (from analysis)",
}: {
  payload: unknown
  title?: string
}) {
  const text = useMemo(() => readInferredNmrText(payload), [payload])
  if (text === null) {
    // Silent when missing so the panel can be dropped into legacy result
    // layouts without forcing every backend response to populate it.
    return null
  }
  return (
    <Card
      className="overflow-hidden rounded-xl py-0"
      style={{ borderTop: "3px solid var(--mt-blue, #4c6fae)" }}
      data-testid="inferred-nmr-text-panel"
    >
      <CardContent className="space-y-2 py-3">
        <div className="flex items-center justify-between">
          <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
            <FileText className="h-3 w-3" aria-hidden />
            {title}
          </p>
          <span className="font-mono text-[10px] text-muted-foreground">
            backend-generated
          </span>
        </div>
        {/* Wrap so long multiplet strings stay readable on narrow cards. The
            text is the user-visible product of the deconvolution + reference-
            guided multiplicity pipeline, so render it verbatim — no
            truncation, no client-side reformatting. */}
        <p
          className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-foreground"
          data-testid="inferred-nmr-text-body"
        >
          {text}
        </p>
      </CardContent>
    </Card>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Proton inventory — observed vs expected counts by chemical class
// ────────────────────────────────────────────────────────────────────────────

/** Rows that compose the inventory tables — pure display, all numbers come
 * straight from the backend's ``build_proton_inventory`` audit. */
const PROTON_INVENTORY_ROWS: Array<{ key: string; label: string }> = [
  { key: "aromatic", label: "Aromatic / vinyl-aryl" },
  // Bucket key renamed from ``olefinic_vinylic`` → ``anomeric_or_olefinic`` —
  // see peak_categorization.build_proton_inventory. Covers anomeric sugar
  // protons (e.g. tobramycin), olefinic CH, and the ambiguous-without-SMILES
  // case.
  { key: "anomeric_or_olefinic", label: "Anomeric / olefinic (4.4–6 ppm)" },
  { key: "aldehyde", label: "Aldehyde (9–10 ppm)" },
  { key: "carboxylic_acid", label: "Carboxylic acid OH (10–13 ppm)" },
  { key: "aliphatic", label: "Aliphatic (incl. O/N-adjacent)" },
  { key: "labile", label: "Labile (OH / NH / SH / COOH)" },
  { key: "non_labile", label: "Non-labile total" },
  { key: "total", label: "Grand total" },
]

export function ProtonInventoryPanel({ payload }: { payload: unknown }) {
  if (!isRecord(payload)) return null
  const inventory = payload.proton_inventory
  if (!isRecord(inventory)) return null
  if (inventory.nucleus !== "1H") return null
  const observed = isRecord(inventory.observed) ? inventory.observed : {}
  const expected = isRecord(inventory.expected) ? inventory.expected : {}
  const deltas = isRecord(inventory.deltas) ? inventory.deltas : {}
  const warningsRaw = inventory.warnings
  const warnings = Array.isArray(warningsRaw)
    ? warningsRaw.filter((w): w is string => typeof w === "string" && w.length > 0)
    : []
  const hasObserved = Object.values(observed).some(
    (v) => typeof v === "number" && v > 0,
  )
  if (!hasObserved && Object.keys(expected).length === 0) return null
  const hasExpected = Object.keys(expected).length > 0

  return (
    <Card
      className="overflow-hidden rounded-xl py-0"
      style={{ borderTop: "3px solid var(--mt-teal)" }}
      data-testid="proton-inventory"
    >
      <CardContent className="space-y-2 py-3">
        <p
          className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
          style={{ color: "var(--mt-teal)" }}
        >
          <Tag className="h-3 w-3" aria-hidden />
          Proton inventory (observed vs structural expectation)
        </p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-[10px] uppercase tracking-wide">Class</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide text-right">Observed ∫H</TableHead>
              {hasExpected ? (
                <>
                  <TableHead className="text-[10px] uppercase tracking-wide text-right">Expected H</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wide text-right">Δ</TableHead>
                </>
              ) : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {PROTON_INVENTORY_ROWS.map((row) => {
              const obs = asNumber(observed[row.key])
              const exp = asNumber(expected[row.key])
              const delta = asNumber(deltas[row.key])
              if (obs === null && exp === null) return null
              const deltaColor =
                delta !== null && Math.abs(delta) >= 1.0 ? "var(--mt-amber)" : undefined
              return (
                <TableRow key={row.key} data-testid={`proton-inventory-${row.key}`}>
                  <TableCell className="text-[11px] text-muted-foreground">{row.label}</TableCell>
                  <TableCell className="font-mono text-xs text-right">
                    {obs !== null ? obs.toFixed(1) : "—"}
                  </TableCell>
                  {hasExpected ? (
                    <>
                      <TableCell className="font-mono text-xs text-right">
                        {exp !== null ? exp.toFixed(0) : "—"}
                      </TableCell>
                      <TableCell
                        className="font-mono text-xs text-right"
                        style={deltaColor ? { color: deltaColor } : undefined}
                      >
                        {delta !== null ? (delta > 0 ? `+${delta.toFixed(1)}` : delta.toFixed(1)) : "—"}
                      </TableCell>
                    </>
                  ) : null}
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
        {hasExpected && isRecord(expected) ? (
          <div className="flex flex-wrap gap-2 pt-1 text-[11px] text-muted-foreground">
            <span>Structural breakdown:</span>
            {(asNumber(expected.oh) ?? 0) > 0 ? (
              <span
                className="rounded-md border px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
                style={{ borderColor: "var(--mt-teal)", color: "var(--mt-teal)" }}
              >
                {asNumber(expected.oh)} OH
              </span>
            ) : null}
            {(asNumber(expected.nh) ?? 0) > 0 ? (
              <span
                className="rounded-md border px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
                style={{ borderColor: "var(--mt-teal)", color: "var(--mt-teal)" }}
              >
                {asNumber(expected.nh)} NH
              </span>
            ) : null}
            {(asNumber(expected.sh) ?? 0) > 0 ? (
              <span
                className="rounded-md border px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
                style={{ borderColor: "var(--mt-teal)", color: "var(--mt-teal)" }}
              >
                {asNumber(expected.sh)} SH
              </span>
            ) : null}
            {asString(expected.labile_subset) ? (
              <span className="font-mono text-[10px] uppercase tracking-wide text-foreground">
                Subset: {asString(expected.labile_subset)}
              </span>
            ) : null}
          </div>
        ) : null}
        {warnings.length > 0 ? (
          <ul className="list-inside list-disc space-y-0.5 text-[11px]" style={{ color: "var(--mt-amber)" }}>
            {warnings.map((warning, idx) => (
              <li key={idx}>{warning}</li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Peak category summary chips
// ────────────────────────────────────────────────────────────────────────────

export function PeakCategorySummaryPanel({ payload }: { payload: unknown }) {
  if (!isRecord(payload)) return null
  const summary = payload.peak_category_summary
  if (!isRecord(summary)) return null
  const entries: Array<[string, number]> = Object.entries(summary).flatMap(([key, value]) =>
    typeof value === "number" && value > 0 ? [[key, value] as [string, number]] : [],
  )
  if (entries.length === 0) return null
  entries.sort((a, b) => b[1] - a[1])
  return (
    <Card
      className="overflow-hidden rounded-xl py-0"
      style={{ borderTop: "3px solid var(--mt-teal)" }}
      data-testid="peak-category-summary"
    >
      <CardContent className="space-y-2 py-3">
        <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
          <Tag className="h-3 w-3" aria-hidden />
          Peak category mix
        </p>
        <div className="flex flex-wrap gap-1.5">
          {entries.map(([category, count]) => {
            const style = categoryStyle(category)
            return (
              <Badge
                key={category}
                variant="outline"
                className="font-mono text-[10px]"
                style={{ borderColor: style.color, backgroundColor: style.bg, color: style.color }}
              >
                {humanizeCategory(category)} · {count}
              </Badge>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Impurity candidates panel
// ────────────────────────────────────────────────────────────────────────────

export function ImpurityCandidatesPanel({ payload }: { payload: unknown }) {
  const candidates = useMemo(() => {
    if (!isRecord(payload)) return []
    const raw = payload.impurity_candidates
    if (!Array.isArray(raw)) return []
    return raw.filter((c): c is RawPeak => isRecord(c))
  }, [payload])

  if (candidates.length === 0) return null

  return (
    <Card
      className="overflow-hidden rounded-xl py-0"
      style={{ borderTop: "3px solid var(--mt-red, #b8474a)" }}
      data-testid="impurity-candidates"
    >
      <CardContent className="space-y-2 py-3">
        <p
          className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
          style={{ color: "var(--mt-red, #b8474a)" }}
        >
          <Beaker className="h-3 w-3" aria-hidden />
          Impurity candidates
          <span className="ml-1 text-muted-foreground">({candidates.length})</span>
        </p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-[10px] uppercase tracking-wide">δ (ppm)</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide">∫ H</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide">Match</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide">Reason</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {candidates.map((c, idx) => {
              const shift = asNumber(c.shift_ppm)
              const integration = asNumber(c.integration_h)
              const lib = isRecord(c.library_match) ? c.library_match : null
              const label = lib ? asString(lib.label) : null
              const expected = lib ? asNumber(lib.expected_ppm) : null
              const delta = lib ? asNumber(lib.delta_ppm) : null
              const kind = lib ? asString(lib.kind) : null
              const reason = asString(c.reason)
              return (
                <TableRow key={idx} data-testid="impurity-candidate-row">
                  <TableCell className="font-mono text-xs">{shift !== null ? shift.toFixed(3) : "—"}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {integration !== null ? integration.toFixed(2) : "—"}
                  </TableCell>
                  <TableCell className="text-xs">
                    {label ? (
                      <span>
                        <span className="font-mono font-bold">{label}</span>
                        {expected !== null ? (
                          <span className="font-mono text-[10px] text-muted-foreground">
                            {" "}({expected.toFixed(2)} ppm{delta !== null ? `, Δ ${delta.toFixed(2)}` : ""}{kind ? `, ${kind}` : ""})
                          </span>
                        ) : null}
                      </span>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell className="text-[11px] text-muted-foreground">{reason ?? "—"}</TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Labile hydrogen reasoning
// ────────────────────────────────────────────────────────────────────────────

export function LabileHydrogenPanel({ payload }: { payload: unknown }) {
  if (!isRecord(payload)) return null
  const summary = payload.labile_hydrogen_summary
  if (!isRecord(summary)) return null
  const expected = asNumber(summary.expected_labile_h) ?? 0
  const expectedOh = asNumber(summary.expected_oh_h) ?? 0
  const expectedNh = asNumber(summary.expected_nh_h) ?? 0
  const expectedSh = asNumber(summary.expected_sh_h) ?? 0
  const subsetLabel = asString(summary.labile_subset)
  const observedRaw = summary.observed_labile_candidates
  const observed = Array.isArray(observedRaw)
    ? observedRaw.filter((p): p is RawPeak => isRecord(p))
    : []
  const notesRaw = summary.notes
  const notes = Array.isArray(notesRaw)
    ? notesRaw.filter((n): n is string => typeof n === "string" && n.length > 0)
    : []
  const confidence = asNumber(summary.confidence)
  if (expected === 0 && observed.length === 0 && notes.length === 0) {
    return null
  }
  // Card header now reflects the EXACT element subset present in the SMILES
  // (e.g. "(OH)" / "(OH/NH)" / "(OH/NH/SH)"). Falls back to the legacy generic
  // when the backend didn't supply per-element counts (older sessions).
  const headerSubset = subsetLabel && subsetLabel.length > 0 ? subsetLabel : "OH / NH / SH"
  return (
    <Card
      className="overflow-hidden rounded-xl py-0"
      style={{ borderTop: "3px solid var(--mt-amber)" }}
      data-testid="labile-hydrogen-summary"
    >
      <CardContent className="space-y-2 py-3">
        <p
          className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
          style={{ color: "var(--mt-amber)" }}
        >
          <AlertTriangle className="h-3 w-3" aria-hidden />
          Labile H reasoning ({headerSubset})
        </p>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <span>
            Expected labile H: <span className="font-mono font-bold text-foreground">{expected}</span>
          </span>
          {/* Per-element breakdown chips — only render the ones that are present. */}
          {expectedOh > 0 ? (
            <span
              className="rounded-md border px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
              style={{ borderColor: "var(--mt-amber)", color: "var(--mt-amber)" }}
            >
              {expectedOh} OH
            </span>
          ) : null}
          {expectedNh > 0 ? (
            <span
              className="rounded-md border px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
              style={{ borderColor: "var(--mt-amber)", color: "var(--mt-amber)" }}
            >
              {expectedNh} NH
            </span>
          ) : null}
          {expectedSh > 0 ? (
            <span
              className="rounded-md border px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
              style={{ borderColor: "var(--mt-amber)", color: "var(--mt-amber)" }}
            >
              {expectedSh} SH
            </span>
          ) : null}
          <span>
            Observed candidates: <span className="font-mono font-bold text-foreground">{observed.length}</span>
          </span>
          {confidence !== null ? (
            <span>
              Confidence:{" "}
              <span className="font-mono font-bold text-foreground">{(confidence * 100).toFixed(0)}%</span>
            </span>
          ) : null}
        </div>
        {observed.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-[10px] uppercase tracking-wide">δ (ppm)</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wide">Mult</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wide">∫ H</TableHead>
                <TableHead className="text-[10px] uppercase tracking-wide">Reason</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {observed.map((peak, idx) => (
                <TableRow key={idx} data-testid="labile-candidate-row">
                  <TableCell className="font-mono text-xs">
                    {asNumber(peak.shift_ppm) !== null ? (asNumber(peak.shift_ppm) as number).toFixed(3) : "—"}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{asString(peak.multiplicity) ?? "—"}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {asNumber(peak.integration_h) !== null
                      ? (asNumber(peak.integration_h) as number).toFixed(2)
                      : "—"}
                  </TableCell>
                  <TableCell className="text-[11px] text-muted-foreground">
                    {asString(peak.reason) ?? "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
        {notes.length > 0 ? (
          <ul className="list-inside list-disc space-y-0.5 text-[11px] text-muted-foreground">
            {notes.map((note, idx) => (
              <li key={idx}>{note}</li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Predicted vs observed
// ────────────────────────────────────────────────────────────────────────────

export function PredictedVsObservedPanel({ payload }: { payload: unknown }) {
  if (!isRecord(payload)) return null
  const rowsRaw = payload.predicted_vs_observed
  if (!Array.isArray(rowsRaw)) return null
  const rows = rowsRaw.filter((r): r is RawPeak => isRecord(r))
  if (rows.length === 0) return null

  const matched = rows.filter((r) => r.status === "matched").length
  const unmatchedPredicted = rows.filter((r) => r.status === "unmatched_predicted").length
  const unmatchedObserved = rows.filter((r) => r.status === "unmatched_observed").length

  return (
    <div data-testid="predicted-vs-observed">
    <ModuleCard
      accent="teal"
      eyebrow="Evidence · Predicted vs Observed"
      title="Predicted vs observed shift comparison"
      icon={Sparkles}
      description={`Matched ${matched} / predicted ${rows.filter((r) => r.status !== "unmatched_observed").length}. ${unmatchedPredicted} predicted peak(s) and ${unmatchedObserved} observed peak(s) are unmatched.`}
    >
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-[10px] uppercase tracking-wide">Status</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide">Pred (ppm)</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide">Obs (ppm)</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide">Δ (ppm)</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide" title="z = (predicted − observed) / σ_DP4, Smith & Goodman 2010">z_DP4</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide" title="DP4 confidence bucket vs. literature tolerance">Conf.</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide">Env</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide">∫ H</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide">Category</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, idx) => {
              const status = asString(row.status) ?? "?"
              const pred = asNumber(row.predicted_ppm)
              const obs = asNumber(row.observed_ppm)
              const delta = asNumber(row.delta_ppm)
              const zDp4 = asNumber(row.z_dp4)
              const conf = asString(row.confidence)
              const env = asString(row.predicted_environment)
              const integration = asNumber(row.observed_integration_h)
              const category = asString(row.category)
              const style = categoryStyle(category)
              const statusBg =
                status === "matched"
                  ? "var(--mt-green-soft)"
                  : status === "unmatched_predicted"
                    ? "rgba(231, 165, 67, 0.12)"
                    : "rgba(184, 71, 74, 0.10)"
              const statusColor =
                status === "matched"
                  ? "var(--mt-green)"
                  : status === "unmatched_predicted"
                    ? "var(--mt-amber)"
                    : "var(--mt-red, #b8474a)"
              const confColor =
                conf === "high"
                  ? "var(--mt-green)"
                  : conf === "medium"
                    ? "var(--mt-amber)"
                    : conf === "low"
                      ? "var(--mt-red, #b8474a)"
                      : "var(--muted-foreground, #888)"
              return (
                <TableRow key={idx} data-testid="predicted-observed-row">
                  <TableCell>
                    <Badge
                      variant="outline"
                      className="font-mono text-[10px]"
                      style={{ borderColor: statusColor, backgroundColor: statusBg, color: statusColor }}
                    >
                      {status.replace(/_/g, " ")}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{pred !== null ? pred.toFixed(3) : "—"}</TableCell>
                  <TableCell className="font-mono text-xs">{obs !== null ? obs.toFixed(3) : "—"}</TableCell>
                  <TableCell className="font-mono text-xs">{delta !== null ? delta.toFixed(3) : "—"}</TableCell>
                  <TableCell className="font-mono text-xs" style={{ color: zDp4 != null && Math.abs(zDp4) > 1 ? "var(--mt-amber)" : undefined }}>
                    {zDp4 !== null ? zDp4.toFixed(2) : "—"}
                  </TableCell>
                  <TableCell>
                    {conf ? (
                      <Badge
                        variant="outline"
                        className="font-mono text-[10px]"
                        style={{ borderColor: confColor, color: confColor }}
                      >
                        {conf}
                      </Badge>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell className="text-[11px] text-muted-foreground">{env ?? "—"}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {integration !== null ? integration.toFixed(2) : "—"}
                  </TableCell>
                  <TableCell>
                    {category ? (
                      <Badge
                        variant="outline"
                        className="font-mono text-[10px]"
                        style={{ borderColor: style.color, backgroundColor: style.bg, color: style.color }}
                      >
                        {humanizeCategory(category)}
                      </Badge>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </ModuleCard>
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// DP4 candidate ranking
// ────────────────────────────────────────────────────────────────────────────

export function DP4RankingPanel({ payload }: { payload: unknown }) {
  if (!isRecord(payload)) return null
  const raw = payload.dp4_ranking
  if (!Array.isArray(raw)) return null
  const rows = raw.filter((r): r is RawPeak => isRecord(r))
  if (rows.length === 0) return null

  return (
    <div data-testid="dp4-ranking">
    <ModuleCard
      accent="teal"
      eyebrow="Evidence · DP4 candidate ranking"
      title="Smith & Goodman 2010 DP4 posterior probability"
      icon={Target}
      description={`Bayesian ranking under a Student's t error model with σ_1H=0.185 ppm (ν=14.18) / σ_13C=2.306 ppm (ν=11.38). Probabilities sum to 1.0 across the candidate list.`}
    >
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-[10px] uppercase tracking-wide">#</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide">Candidate</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide">DP4 prob.</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide">Matched</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide">MAE (ppm)</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide">RMSE (ppm)</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wide">Scaling</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, idx) => {
              const label = asString(row.candidate_label) ?? `candidate ${idx + 1}`
              const prob = asNumber(row.dp4_probability) ?? 0
              const matched = asNumber(row.matched_peaks)
              const mae = asNumber(row.mean_abs_error_ppm)
              const rmse = asNumber(row.rms_error_ppm)
              const slope = asNumber(row.scaling_slope)
              const intercept = asNumber(row.scaling_intercept)
              const isWinner = idx === 0 && prob > 0
              const tint = isWinner ? "var(--mt-teal)" : "var(--muted-foreground, #888)"
              return (
                <TableRow key={idx} data-testid="dp4-ranking-row">
                  <TableCell className="font-mono text-xs" style={{ color: tint }}>
                    {idx + 1}
                  </TableCell>
                  <TableCell className="font-mono text-xs" style={{ color: isWinner ? tint : undefined, fontWeight: isWinner ? 700 : 400 }}>
                    {label}
                  </TableCell>
                  <TableCell>
                    <div className="space-y-1">
                      <span
                        className="font-mono text-xs font-bold tabular-nums"
                        style={{ color: tint }}
                      >
                        {Math.round(prob * 100)}%
                      </span>
                      <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{ width: `${Math.max(0, Math.min(100, prob * 100))}%`, backgroundColor: tint }}
                        />
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{matched != null ? matched : "—"}</TableCell>
                  <TableCell className="font-mono text-xs">{mae != null ? mae.toFixed(3) : "—"}</TableCell>
                  <TableCell className="font-mono text-xs">{rmse != null ? rmse.toFixed(3) : "—"}</TableCell>
                  <TableCell className="font-mono text-[10px] text-muted-foreground">
                    {slope != null && intercept != null
                      ? `δ_obs = ${slope.toFixed(3)}·δ_pred ${intercept >= 0 ? "+" : "−"} ${Math.abs(intercept).toFixed(3)}`
                      : "—"}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </ModuleCard>
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// References / citation block
// ────────────────────────────────────────────────────────────────────────────

export function ReferencesPanel({ payload }: { payload: unknown }) {
  if (!isRecord(payload)) return null
  const raw = payload.references
  if (!Array.isArray(raw)) return null
  const refs = raw.filter((r): r is RawPeak => isRecord(r))
  if (refs.length === 0) return null
  return (
    <Card
      className="overflow-hidden rounded-xl py-0"
      style={{ borderTop: "3px solid var(--mt-teal)" }}
      data-testid="references-panel"
    >
      <CardContent className="space-y-2 py-3">
        <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
          <BookOpen className="h-3 w-3" aria-hidden />
          References used by this analysis
        </p>
        <ol className="list-inside list-decimal space-y-1 text-[11px] text-muted-foreground">
          {refs.map((r, idx) => {
            const title = asString(r.title)
            const authors = asString(r.authors)
            const venue = asString(r.venue)
            const year = asNumber(r.year)
            const doi = asString(r.doi)
            const url = asString(r.url)
            const href = doi ? `https://doi.org/${doi}` : (url ?? null)
            const display = (
              <span>
                {authors ? <span className="font-medium text-foreground">{authors}</span> : null}
                {authors ? ". " : null}
                {title ? <span className="italic">{title}</span> : null}
                {title ? ". " : null}
                {venue ? <span>{venue}</span> : null}
                {year ? <span> {year}</span> : null}
                {doi ? <span className="ml-1 font-mono text-[10px]">doi:{doi}</span> : null}
              </span>
            )
            return (
              <li key={idx}>
                {href ? (
                  <a href={href} target="_blank" rel="noopener noreferrer" className="hover:underline">
                    {display}
                  </a>
                ) : (
                  display
                )}
              </li>
            )
          })}
        </ol>
      </CardContent>
    </Card>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Composite — drop in below the spectrum
// ────────────────────────────────────────────────────────────────────────────

function SpectraCheckEvidencePanelsImpl({ payload }: { payload: unknown }) {
  return (
    <div className="space-y-4">
      <PeakCategorySummaryPanel payload={payload} />
      {/* Proton inventory sits beside peak-category chips so reviewers can
          cross-check observed integrations against the structural prediction
          before drilling into individual peak panels. */}
      <ProtonInventoryPanel payload={payload} />
      <div className="grid min-w-0 gap-4 lg:grid-cols-2">
        <LabileHydrogenPanel payload={payload} />
        <ImpurityCandidatesPanel payload={payload} />
      </div>
      <DP4RankingPanel payload={payload} />
      <PredictedVsObservedPanel payload={payload} />
      <ReferencesPanel payload={payload} />
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Memoised exports
// ────────────────────────────────────────────────────────────────────────────
//
// The two composite-facing panels (``EnrichedPickedPeaksPanel`` and
// ``SpectraCheckEvidencePanels``) are mounted in the Step-3 results card
// under the spectrum. The section component now passes a deferred payload
// reference to both, so re-renders triggered by unrelated state churn
// (typing in Sample ID, gain-slider drag) hand them the SAME object
// reference. Wrapping in ``React.memo`` short-circuits the entire panel
// tree in that case — the chart and toolbar can repaint without
// invalidating the picked-peaks table, DP4 ranking, predicted-vs-observed
// table, impurity candidates, references, etc.
export const EnrichedPickedPeaksPanel = memo(EnrichedPickedPeaksPanelImpl)
export const InferredNmrTextPanel = memo(InferredNmrTextPanelImpl)
export const SpectraCheckEvidencePanels = memo(SpectraCheckEvidencePanelsImpl)

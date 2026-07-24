"use client"

/**
 * Repho Phase C / R14 — forward check ("check a predicted/planned product before acting on it").
 *
 * The value proposition: model confidence is NOT a safety opinion — the two render side-by-side
 * so a high-confidence prediction with an energetic-group hit reads as exactly what it is.
 * Forward GENERATION is an unwired heavy path; input here is an externally-predicted/planned
 * product by design.
 */
import { useState } from "react"
import { FlaskConical } from "lucide-react"
import { ApiError } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  parseForwardCheckRecord,
  parseSmilesList,
  postForwardCheck,
  routeRiskBadgeClass,
  routeRiskLabel,
  type ForwardCheckView,
} from "@/lib/reaction/phase-c"

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v)
}

export function ForwardCheckPanel({ projectId }: { projectId: number }) {
  const [reactantsText, setReactantsText] = useState("")
  const [productsText, setProductsText] = useState("")
  const [reagentsText, setReagentsText] = useState("")
  const [confidenceText, setConfidenceText] = useState("")
  const [label, setLabel] = useState("")
  const [busy, setBusy] = useState(false)
  const [inputError, setInputError] = useState("")
  const [msg, setMsg] = useState("")
  const [view, setView] = useState<ForwardCheckView | null>(null)

  async function check(e: React.FormEvent) {
    e.preventDefault()
    setMsg("")
    const reactants = parseSmilesList(reactantsText)
    const products = parseSmilesList(productsText)
    if (reactants.length === 0) {
      setInputError("At least one reactant SMILES is required.")
      return
    }
    if (products.length === 0) {
      setInputError("At least one product SMILES is required — this checks a predicted/planned product.")
      return
    }
    const reagentsPre = parseSmilesList(reagentsText)
    const overLimit = [
      reactants.length > 50 ? "reactants" : "",
      products.length > 50 ? "products" : "",
      reagentsPre.length > 50 ? "reagents" : "",
    ].filter(Boolean)
    if (overLimit.length > 0) {
      setInputError(`At most 50 SMILES per list — too many: ${overLimit.join(", ")}.`)
      return
    }
    if (label.trim().length > 200) {
      setInputError("label must be 200 characters or fewer.")
      return
    }
    const confRaw = confidenceText.trim()
    let confidence: number | undefined
    if (confRaw !== "") {
      const n = Number(confRaw)
      if (!Number.isFinite(n) || n < 0 || n > 1) {
        setInputError("confidence must be a number between 0 and 1 (or leave it blank).")
        return
      }
      confidence = n
    }
    setInputError("")
    setBusy(true)
    try {
      const body: Parameters<typeof postForwardCheck>[1] = {
        reactants_smiles: reactants,
        products_smiles: products,
      }
      const reagents = parseSmilesList(reagentsText)
      if (reagents.length > 0) body.reagents_smiles = reagents
      if (confidence != null) body.confidence = confidence
      if (label.trim()) body.label = label.trim()
      const created = await postForwardCheck(projectId, body)
      setView(parseForwardCheckRecord(created))
    } catch (err) {
      if (
        err instanceof ApiError &&
        (err.status === 400 || err.status === 422) &&
        isRecord(err.data)
      ) {
        const detail = err.data.detail
        // A 422 detail is an array of field errors — apiFetch already formats it into err.message,
        // so fall back to that rather than discarding the specific limit/field message.
        setInputError(
          typeof detail === "string"
            ? detail
            : err.message || "The check was rejected — verify the SMILES lists and try again.",
        )
      } else {
        setMsg(formatApiError(err, "POST …/forward-checks failed."))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <ModuleCard
      accent="teal"
      eyebrow="Safety · Forward check"
      title="Check a predicted product"
      icon={FlaskConical}
      description="Annotate an externally-predicted or planned product with the frozen safety and green-chemistry engines before acting on it. Model confidence is NOT a safety opinion — both render side-by-side. Advisory decision support; a qualified chemist reviews every prediction."
    >
      <form className="space-y-3" onSubmit={(e) => void check(e)}>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="fc-reactants" className="text-xs">reactant SMILES (comma/newline separated)</Label>
            <Textarea
              id="fc-reactants"
              rows={2}
              className="font-mono text-xs"
              value={reactantsText}
              onChange={(e) => setReactantsText(e.target.value)}
              placeholder="Oc1ccccc1C(=O)O, CC(=O)OC(C)=O"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="fc-products" className="text-xs">predicted/planned product SMILES</Label>
            <Textarea
              id="fc-products"
              rows={2}
              className="font-mono text-xs"
              value={productsText}
              onChange={(e) => setProductsText(e.target.value)}
              placeholder="CC(=O)Oc1ccccc1C(=O)O"
            />
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <div className="space-y-1">
            <Label htmlFor="fc-reagents" className="text-xs">reagent SMILES (optional)</Label>
            <Input
              id="fc-reagents"
              className="h-8 font-mono text-xs"
              value={reagentsText}
              onChange={(e) => setReagentsText(e.target.value)}
              placeholder="O=S(=O)(O)O"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="fc-confidence" className="text-xs">model confidence 0–1 (optional)</Label>
            <Input
              id="fc-confidence"
              className="h-8 text-xs"
              inputMode="decimal"
              value={confidenceText}
              onChange={(e) => setConfidenceText(e.target.value)}
              placeholder="0.87"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="fc-label" className="text-xs">label (optional)</Label>
            <Input
              id="fc-label"
              className="h-8 text-xs"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="acylation product check"
            />
          </div>
        </div>
        {inputError ? (
          <p role="alert" className="text-[11px] text-destructive">
            {inputError}
          </p>
        ) : null}
        <Button type="submit" size="sm" disabled={busy}>
          {busy ? "Checking…" : "Run forward check"}
        </Button>
      </form>
      {msg ? (
        <p role="status" className="mt-3 text-xs text-muted-foreground">
          {msg}
        </p>
      ) : null}
      {view != null ? (
        <div className="mt-4 space-y-3 rounded-md border p-3">
          <div className="flex flex-wrap items-center gap-2">
            {view.label ? <p className="text-sm font-medium text-foreground">{view.label}</p> : null}
            <Badge variant="secondary" className="text-xs">advisory</Badge>
          </div>
          {/* Confidence and the safety verdict SIDE-BY-SIDE: confidence is not a safety opinion. */}
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-md border px-3 py-2">
              <p className="font-mono text-sm tabular-nums">
                {view.confidence != null ? view.confidence.toFixed(2) : "—"}
              </p>
              <p className="text-[10px] text-muted-foreground">model confidence (NOT a safety opinion)</p>
            </div>
            <div className="rounded-md border px-3 py-2">
              <Badge className={`text-xs ${routeRiskBadgeClass(view.overallRisk)}`}>
                {routeRiskLabel(view.overallRisk)}
              </Badge>
              <p className="mt-1 text-[10px] text-muted-foreground">
                safety verdict{view.requiresExpertReview ? " — expert review required" : ""}
              </p>
            </div>
          </div>
          <div className="min-w-0 space-y-1 text-[11px] text-muted-foreground">
            <p className="min-w-0">
              products:{" "}
              <span className="break-all font-mono text-foreground">
                {view.productsSmiles.join(", ") || "—"}
              </span>
            </p>
            {view.energeticGroupsFound.length > 0 ? (
              <p className="min-w-0 font-medium text-foreground">
                energetic groups found:{" "}
                <span className="break-all font-mono">{view.energeticGroupsFound.join(", ")}</span>
              </p>
            ) : null}
            {view.solventGreenness != null ? (
              <p>
                solvent greenness: <span className="font-mono text-foreground">{view.solventGreenness}</span>
              </p>
            ) : null}
          </div>
          {view.warnings.length > 0 ? (
            <ul className="list-inside list-disc text-[11px] text-muted-foreground">
              {view.warnings.map((w, i) => (
                <li key={`fc-w-${i}`}>{w}</li>
              ))}
            </ul>
          ) : null}
          {view.humanReviewRequired ? (
            <p className="text-[11px] font-medium text-foreground">
              Human review required — a qualified chemist reviews every prediction before any action.
            </p>
          ) : null}
          {view.disclaimer ? (
            <p className="text-[11px] italic text-muted-foreground">{view.disclaimer}</p>
          ) : null}
        </div>
      ) : null}
    </ModuleCard>
  )
}

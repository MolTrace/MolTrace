export type Summary = {
  bestCandidate: string
  candidateCount: number | null
  confidence: number | null
  evidenceLayers: string[]
  warnings: string[]
  contradictions: string[]
  notes: string[]
  rankedCandidates: Record<string, unknown>[]
  humanReviewLabel: string | null
  panels: {
    showBestCandidate: boolean
    showRankedTable: boolean
    showEvidenceLayers: boolean
    showWarnings: boolean
    showNotes: boolean
    showContradictions: boolean
    showHumanReview: boolean
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function walk(value: unknown, visit: (key: string, nestedValue: unknown) => void, key = "", depth = 0) {
  if (depth > 5) return

  if (Array.isArray(value)) {
    value.forEach((item) => walk(item, visit, key, depth + 1))
    return
  }

  if (!isRecord(value)) return

  Object.entries(value).forEach(([nestedKey, nestedValue]) => {
    visit(nestedKey, nestedValue)
    walk(nestedValue, visit, nestedKey, depth + 1)
  })
}

function formatCandidate(value: unknown): string {
  if (typeof value === "string") return value
  if (!isRecord(value)) return "Returned by backend"

  const nestedAdduct = value.adduct
  if (isRecord(nestedAdduct) && typeof nestedAdduct.name === "string" && nestedAdduct.name.length > 0) {
    const neutral = typeof value.neutral_mass === "number" ? value.neutral_mass.toFixed(5) : null
    return neutral ? `${nestedAdduct.name} · neutral ${neutral}` : nestedAdduct.name
  }

  const fields = ["name", "candidate_name", "label", "formula", "smiles", "id"]
    .map((field) => value[field])
    .filter((field): field is string => typeof field === "string" && field.length > 0)

  return fields.length > 0 ? fields.slice(0, 3).join(" · ") : "Returned by backend"
}

function findCandidateArray(data: unknown): unknown[] | null {
  let candidates: unknown[] | null = null

  walk(data, (key, value) => {
    if (candidates) return
    if (!Array.isArray(value) || value.length === 0) return
    if (/candidate|ranking|result/i.test(key)) {
      candidates = value
    }
  })

  return candidates
}

export function summarizeResult(data: unknown): Summary {
  const candidateArray = findCandidateArray(data)
  let bestCandidate = candidateArray?.[0] ? formatCandidate(candidateArray[0]) : "Not provided"
  let confidence: number | null = null
  let humanReviewLabel: string | null = null
  const evidenceLayers = new Set<string>()
  const warnings = new Set<string>()
  const contradictions = new Set<string>()
  const notes = new Set<string>()
  let rankedCandidates: Record<string, unknown>[] = []

  if (isRecord(data)) {
    const directRanked = data.ranked_candidates
    if (Array.isArray(directRanked)) {
      rankedCandidates = directRanked.filter(isRecord)
    }
    if (rankedCandidates.length === 0 && Array.isArray(data.formulas)) {
      rankedCandidates = data.formulas.filter(isRecord)
    }
    if (rankedCandidates.length === 0 && Array.isArray(data.adduct_candidates)) {
      rankedCandidates = data.adduct_candidates.filter(isRecord)
    }
  }

  walk(data, (key, value) => {
    if (/best_?(candidate|match)|best_adduct_candidate|top_?candidate/i.test(key)) {
      bestCandidate = formatCandidate(value)
    }

    if (confidence === null && /confidence|score/i.test(key) && typeof value === "number") {
      confidence = value <= 1 ? value * 100 : value
    }

    if (/nmr|msms|ms\/ms|lcms|lc_ms|evidence|formula|adduct|regulatory/i.test(key)) {
      evidenceLayers.add(key.replaceAll("_", " "))
    }

    if (/evidence_layers_used/i.test(key)) {
      if (Array.isArray(value)) {
        value.forEach((layer) => evidenceLayers.add(String(layer).replaceAll("_", " ")))
      } else if (typeof value === "string") {
        evidenceLayers.add(value.replaceAll("_", " "))
      }
    }

    if (/human_review|review_state|review_status|qc_status|approval_status|needs_review|human\s*qc/i.test(key)) {
      if (humanReviewLabel === null) {
        if (typeof value === "string" && value.trim()) humanReviewLabel = value.trim()
        else if (isRecord(value)) {
          const rs =
            value.status ?? value.state ?? value.label ?? value.decision ?? value.result ?? value.phase
          if (typeof rs === "string" && rs.trim()) humanReviewLabel = rs.trim()
        }
      }
    }

    if (/contradiction|conflict|inconsistent|mutually_exclusive/i.test(key)) {
      if (typeof value === "string") contradictions.add(value)
      if (Array.isArray(value)) {
        value.slice(0, 8).forEach((item) =>
          contradictions.add(typeof item === "string" ? item : JSON.stringify(item))
        )
      } else if (isRecord(value)) {
        contradictions.add(JSON.stringify(value))
      }
    }

    if (
      /warning|limitation|caution|error/i.test(key) &&
      !/contradiction|conflict|inconsistent/i.test(key)
    ) {
      if (typeof value === "string") warnings.add(value)
      if (Array.isArray(value)) {
        value.slice(0, 6).forEach((item) => warnings.add(typeof item === "string" ? item : JSON.stringify(item)))
      }
    }

    if (/notes?/i.test(key)) {
      if (typeof value === "string") notes.add(value)
      if (Array.isArray(value)) {
        value.slice(0, 6).forEach((item) => notes.add(typeof item === "string" ? item : JSON.stringify(item)))
      }
    }
  })

  const tl = isRecord(data) ? data : null
  const rankedFromApi = tl && Array.isArray(tl.ranked_candidates) ? tl.ranked_candidates.length : 0
  const warningsFromApi =
    tl &&
    (Array.isArray(tl.warnings)
      ? tl.warnings.length > 0
      : typeof tl.warnings === "string"
        ? tl.warnings.length > 0
        : false)
  const notesFromApi =
    tl &&
    (Array.isArray(tl.notes)
      ? tl.notes.length > 0
      : typeof tl.notes === "string"
        ? tl.notes.length > 0
        : false)
  const evidenceFromApi =
    tl &&
    (Array.isArray(tl.evidence_layers_used)
      ? tl.evidence_layers_used.length > 0
      : typeof tl.evidence_layers_used === "string"
        ? tl.evidence_layers_used.length > 0
        : false)

  const contradictionsList = Array.from(contradictions)
  const warningsList = Array.from(warnings)
  const notesList = Array.from(notes)

  let resolvedBest = bestCandidate
  if (resolvedBest === "Not provided" && rankedCandidates.length > 0) {
    resolvedBest = formatCandidate(rankedCandidates[0])
  }

  const showRankedTable = rankedCandidates.length > 0 || rankedFromApi > 0
  const hasExplicitBest = Boolean(
    tl &&
      (tl.best_candidate != null ||
        tl.bestCandidate != null ||
        tl.best_match != null ||
        tl.best_adduct_candidate != null),
  )
  const showBestCandidate = hasExplicitBest || resolvedBest !== "Not provided"
  const showEvidenceLayers = evidenceFromApi || evidenceLayers.size > 0
  const showWarnings = warningsFromApi || warningsList.length > 0
  const showNotes = notesFromApi || notesList.length > 0
  const showContradictions = contradictionsList.length > 0
  const showHumanReview = humanReviewLabel != null

  return {
    bestCandidate: resolvedBest,
    candidateCount:
      rankedCandidates.length > 0
        ? rankedCandidates.length
        : typeof tl?.candidate_count === "number"
          ? tl.candidate_count
          : typeof tl?.formula_count === "number"
            ? tl.formula_count
            : candidateArray?.length ?? null,
    confidence,
    evidenceLayers: Array.from(evidenceLayers).slice(0, 8),
    warnings: warningsList.slice(0, 8),
    contradictions: contradictionsList.slice(0, 8),
    notes: notesList.slice(0, 6),
    rankedCandidates,
    humanReviewLabel,
    panels: {
      showBestCandidate,
      showRankedTable,
      showEvidenceLayers,
      showWarnings,
      showNotes,
      showContradictions,
      showHumanReview,
    },
  }
}

export function candidateLabel(candidate: Record<string, unknown>, index: number) {
  const values = ["name", "candidate_name", "label", "formula", "smiles", "id"]
    .map((field) => candidate[field])
    .filter((value): value is string => typeof value === "string" && value.length > 0)
  return values.length > 0 ? values[0] : `Candidate ${index + 1}`
}

export function candidateScore(candidate: Record<string, unknown>) {
  const raw =
    candidate.score ??
    candidate.tree_score ??
    candidate.candidate_score ??
    candidate.precursor_score ??
    candidate.ppm_score ??
    candidate.confidence
  if (typeof raw === "number") return raw <= 1 ? raw * 100 : raw
  return null
}

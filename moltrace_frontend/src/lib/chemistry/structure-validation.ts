import { apiFetch } from "@/lib/api/client"
import type { components } from "@/src/lib/api/schema"

/**
 * The structure & reaction-scheme service: the thing that turns a drawing into a checked
 * structure. Types come from the generated schema, so a contract change breaks the build here
 * rather than at runtime in a chemist's face.
 */

export type StructureIssue = components["schemas"]["StructureIssue"]
export type StructureValidateResponse = components["schemas"]["StructureValidateResponse"]
export type StructureComponentCounts = components["schemas"]["StructureComponentCounts"]
export type ReactionStructureScheme = components["schemas"]["ReactionStructureScheme"]
export type StructureFormat = StructureValidateResponse["format"]

/** The exact snapshot fields the request accepts. Every model here is extra="forbid". */
export type StructureSnapshotInput = {
  block: string
  format: StructureFormat
  /** May be "" — that is the expected value for query and R-group drawings. */
  smiles: string
}

function requestBody(snapshot: StructureSnapshotInput) {
  // block / format / smiles and NOTHING else: an undeclared key is a 422 for the whole request.
  return { block: snapshot.block, format: snapshot.format, smiles: snapshot.smiles ?? "" }
}

/**
 * Check a drawing.
 *
 * A structure that fails its chemistry checks is a SUCCESSFUL request carrying `ok: false` and a
 * populated `errors[]` — the verdict is in the body, not the status code. Only a malformed or
 * oversized request is a 4xx, and that throws.
 */
export async function validateStructure(
  snapshot: StructureSnapshotInput,
): Promise<StructureValidateResponse> {
  return apiFetch<StructureValidateResponse>("/reactions/structures/validate", {
    method: "POST",
    body: requestBody(snapshot),
  })
}

/**
 * Attach a checked scheme to a reaction project.
 *
 * A drawing RDKit cannot read is refused with 400 rather than stored — attaching it would let the
 * rest of the product treat an unchecked structure as checked. That message is already written for
 * a chemist, so callers render it as-is.
 */
export async function attachReactionScheme(
  reactionProjectId: number,
  snapshot: StructureSnapshotInput,
  name: string,
): Promise<ReactionStructureScheme> {
  const trimmed = name.trim()
  return apiFetch<ReactionStructureScheme>(
    `/reaction-projects/${encodeURIComponent(String(reactionProjectId))}/schemes`,
    {
      method: "POST",
      body: { ...requestBody(snapshot), name: trimmed || null, metadata_json: {} },
    },
  )
}

export type IssueSeverity = "error" | "warning"

/**
 * Codes worth pulling out of the list, because they are the reason this service exists: the first
 * says the editor's own SMILES disagrees with the drawing it came from, the second says what would
 * be stored is not what was drawn. Both are silent data corruption if nobody looks.
 */
export const HEADLINE_WARNING_CODES = ["drawn_smiles_differs", "hydrogen_count_changed"] as const

export function isHeadlineWarning(issue: StructureIssue): boolean {
  return (HEADLINE_WARNING_CODES as readonly string[]).includes(issue.code)
}

/** Issues the reader should see first, without dropping any: headline codes float to the top. */
export function orderIssues(issues: readonly StructureIssue[]): StructureIssue[] {
  const headline = issues.filter(isHeadlineWarning)
  const rest = issues.filter((i) => !isHeadlineWarning(i))
  return [...headline, ...rest]
}

export type StructureVerdict = {
  ok: boolean
  errors: StructureIssue[]
  warnings: StructureIssue[]
  canonicalSmiles: string | null
  normalizedBlock: string | null
  inchikey: string | null
  atomCount: number
  bondCount: number
  componentCounts: StructureComponentCounts | null
  validatorVersion: string | null
  /** True when the service said the drawing is sound and had nothing at all to flag. */
  clean: boolean
}

function nonEmpty(v: string | null | undefined): string | null {
  return typeof v === "string" && v.trim() ? v.trim() : null
}

/**
 * Read the response defensively. The verdict drives what the UI is allowed to claim, so a missing
 * or malformed field must never read as "fine": `ok` counts only when it is literally true.
 */
export function readVerdict(response: unknown): StructureVerdict | null {
  if (!response || typeof response !== "object" || Array.isArray(response)) return null
  const r = response as Partial<StructureValidateResponse>
  const errors = Array.isArray(r.errors) ? r.errors.filter(isIssue) : []
  const warnings = Array.isArray(r.warnings) ? r.warnings.filter(isIssue) : []
  const ok = r.ok === true
  return {
    ok,
    errors: orderIssues(errors),
    warnings: orderIssues(warnings),
    canonicalSmiles: nonEmpty(r.canonical_smiles),
    normalizedBlock: nonEmpty(r.normalized_block),
    inchikey: nonEmpty(r.inchikey),
    atomCount: typeof r.atom_count === "number" && Number.isFinite(r.atom_count) ? r.atom_count : 0,
    bondCount: typeof r.bond_count === "number" && Number.isFinite(r.bond_count) ? r.bond_count : 0,
    componentCounts: readComponentCounts(r.component_counts),
    validatorVersion: nonEmpty(r.validator_version),
    clean: ok && errors.length === 0 && warnings.length === 0,
  }
}

function isIssue(v: unknown): v is StructureIssue {
  if (!v || typeof v !== "object" || Array.isArray(v)) return false
  const o = v as Record<string, unknown>
  return typeof o.code === "string" && typeof o.message === "string"
}

function readComponentCounts(v: unknown): StructureComponentCounts | null {
  // Populated only for reactions; absent for a single structure rather than zeroed.
  if (!v || typeof v !== "object" || Array.isArray(v)) return null
  const o = v as Record<string, unknown>
  const num = (k: string) => (typeof o[k] === "number" && Number.isFinite(o[k]) ? (o[k] as number) : 0)
  return { reactants: num("reactants"), agents: num("agents"), products: num("products") }
}

/**
 * 0-based positions in the drawing's atom list, for highlighting.
 *
 * For a reaction these are positions WITHIN the component the message names ("In reactant 2, …"),
 * not across the whole scheme — so they must never be presented as scheme-wide atom numbers.
 */
export function issueAtomIndices(issue: StructureIssue): number[] {
  return Array.isArray(issue.atom_indices)
    ? issue.atom_indices.filter((n): n is number => typeof n === "number" && Number.isFinite(n))
    : []
}

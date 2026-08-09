/**
 * "Approved" and "serving" are two different facts about a model artifact, and until the
 * registry fields existed a listing could only show the first — so an artifact approved for
 * the product read as one answering predictions.
 *
 * Approval is a product decision. Whether predictions actually resolve to the artifact is a
 * separate one, held in the science model registry, which resolves exactly one lifecycle
 * state: `production`. Everything else there (`candidate`, `shadow`, `retired`) is registered
 * but not answering, and an artifact with no registry entry is not serving whatever its
 * `status` says. Where the two disagree, the registry is the authoritative one.
 */

export type RegistryStatus = "candidate" | "shadow" | "production" | "retired"

const REGISTRY_STATUSES: readonly RegistryStatus[] = [
  "candidate",
  "shadow",
  "production",
  "retired",
]

/** The only registry state predictions resolve to. */
export const SERVING_REGISTRY_STATUS: RegistryStatus = "production"

/** The artifact `status` that would otherwise be misread as "deployed". */
const APPROVED_ARTIFACT_STATUS = "approved"

export type ServingState = {
  registryModelId: string | null
  registryStatus: RegistryStatus | null
  role: string | null
  /** `null` means the entry serves every nucleus. */
  nucleus: string | null
  approvalStatus: string | null
  /** True only when predictions actually resolve to this artifact. */
  serving: boolean
  /** Reader-facing serving state. Never a bare wire token. */
  label: string
  /** Why it is, or is not, serving. */
  detail: string
  /** Approved for the product, but not answering — the state that used to read as deployed. */
  contradictsApproval: boolean
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readString(row: Record<string, unknown>, key: string): string | null {
  const v = row[key]
  if (typeof v === "string" && v.trim()) return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return null
}

function readRegistryStatus(row: Record<string, unknown>): RegistryStatus | null {
  const raw = readString(row, "registry_status")
  if (raw == null) return null
  return REGISTRY_STATUSES.includes(raw as RegistryStatus) ? (raw as RegistryStatus) : null
}

/** "13C" or, for an entry that serves every nucleus, an explicit statement of that. */
export function nucleusScopeLabel(nucleus: string | null): string {
  return nucleus ?? "All nuclei"
}

function servingDetail(
  status: RegistryStatus | null,
  role: string | null,
  nucleus: string | null,
): string {
  // Never case-fold the nucleus: "13C" is a name, and "13c" is a different thing entirely.
  const scope = role ? ` for ${role} · ${nucleus ?? "all nuclei"}` : ""
  switch (status) {
    case "production":
      return `Predictions resolve to this artifact${scope}.`
    case "shadow":
      return "Registered for shadow evaluation only — no prediction resolves to it."
    case "candidate":
      return "Registered as a candidate — no prediction resolves to it."
    case "retired":
      return "Superseded by a later promotion — no prediction resolves to it."
    default:
      return "Not in the model registry, so no prediction resolves to it."
  }
}

function servingLabel(status: RegistryStatus | null): string {
  switch (status) {
    case "production":
      return "Serving"
    case "shadow":
      return "Shadow only"
    case "candidate":
      return "Registered, not serving"
    case "retired":
      return "Retired"
    default:
      return "Not serving"
  }
}

/**
 * Read the serving facts off a model-artifact row. Safe on a row from any older response
 * that carries none of the registry fields — that reads as "not serving", which is correct:
 * an artifact the registry has never heard of is not answering predictions.
 */
export function readServingState(row: unknown): ServingState {
  const record = isRecord(row) ? row : {}
  const registryModelId = readString(record, "registry_model_id")
  const registryStatus = readRegistryStatus(record)
  const role = readString(record, "registry_role")
  const nucleus = readString(record, "registry_nucleus")
  const approvalStatus = readString(record, "status")

  // Both halves have to hold: a registry entry that exists but sits in `shadow` is not
  // answering, and a `production` status with no entry id is not a thing the router can
  // resolve. Requiring both keeps a partially-populated row from reading as live.
  const serving = registryModelId != null && registryStatus === SERVING_REGISTRY_STATUS

  return {
    registryModelId,
    registryStatus,
    role,
    nucleus,
    approvalStatus,
    serving,
    label: servingLabel(registryStatus),
    detail: servingDetail(registryStatus, role, nucleus),
    contradictsApproval: !serving && approvalStatus === APPROVED_ARTIFACT_STATUS,
  }
}

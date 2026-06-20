// Reusable option loaders for <EntityPicker> — turn a list endpoint into named
// {id, label, description} options so forms never make a user type a raw id.

import { apiFetch } from "@/lib/api/client"
import type { EntityOption } from "@/components/ui/entity-picker"

function isRecord(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === "object" && !Array.isArray(v)
}
function asArray(raw: unknown): unknown[] {
  if (Array.isArray(raw)) return raw
  if (isRecord(raw)) {
    for (const k of ["items", "results", "rows", "data", "compounds", "projects"]) {
      if (Array.isArray(raw[k])) return raw[k] as unknown[]
    }
  }
  return []
}
function readId(v: unknown): number | string | null {
  if (typeof v === "number" && Number.isFinite(v)) return v
  if (typeof v === "string" && v.trim() !== "") return v
  return null
}
function str(v: unknown): string {
  return typeof v === "string" && v.trim() !== "" ? v.trim() : ""
}

export async function loadReactionProjects(): Promise<EntityOption[]> {
  const raw = await apiFetch<unknown>("/reaction-projects", { method: "GET" })
  const out: EntityOption[] = []
  for (const r of asArray(raw)) {
    if (!isRecord(r)) continue
    const id = readId(r.id ?? r.reaction_project_id)
    if (id == null) continue
    out.push({ id, label: str(r.name) || `Project ${id}`, description: str(r.objective) || undefined })
  }
  return out
}

export async function loadValidationProjects(): Promise<EntityOption[]> {
  const raw = await apiFetch<unknown>("/validation-center/projects", { method: "GET" })
  const out: EntityOption[] = []
  for (const r of asArray(raw)) {
    if (!isRecord(r)) continue
    const id = readId(r.id ?? r.validation_project_id)
    if (id == null) continue
    out.push({ id, label: str(r.title) || `Validation project ${id}`, description: str(r.validation_type) || undefined })
  }
  return out
}

export async function loadOrganizations(): Promise<EntityOption[]> {
  const raw = await apiFetch<unknown>("/organizations", { method: "GET" })
  const out: EntityOption[] = []
  for (const r of asArray(raw)) {
    if (!isRecord(r)) continue
    const id = readId(r.id ?? r.organization_id)
    if (id == null) continue
    out.push({ id, label: str(r.name) || `Organization ${id}`, description: str(r.slug) || undefined })
  }
  return out
}

export async function loadDossiers(): Promise<EntityOption[]> {
  const raw = await apiFetch<unknown>("/regulatory/dossiers", { method: "GET" })
  const out: EntityOption[] = []
  for (const r of asArray(raw)) {
    if (!isRecord(r)) continue
    const id = readId(r.id ?? r.dossier_id)
    if (id == null) continue
    out.push({
      id,
      label: str(r.title) || str(r.product_name) || `Dossier ${id}`,
      description: str(r.product_name) || str(r.compound_name) || undefined,
    })
  }
  return out
}

export async function loadCompounds(): Promise<EntityOption[]> {
  const raw = await apiFetch<unknown>("/compound-registry/compounds", { method: "GET" })
  const out: EntityOption[] = []
  for (const r of asArray(raw)) {
    if (!isRecord(r)) continue
    const id = readId(r.id ?? r.compound_id)
    if (id == null) continue
    const code = str(r.registry_number) || str(r.compound_code) || str(r.cas_number)
    out.push({
      id,
      label: str(r.preferred_name) || str(r.name) || `Compound ${id}`,
      description: code || undefined,
    })
  }
  return out
}

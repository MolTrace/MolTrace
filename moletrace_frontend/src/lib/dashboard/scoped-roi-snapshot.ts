import { apiFetch } from "@/lib/api/client"
import { parseRoiSnapshot, type RoiSnapshotData } from "@/src/lib/analytics/roi-dashboard-data"

/** GET /analytics/projects/{project_id}/roi */
export async function fetchProjectRoiSnapshot(projectId: string): Promise<RoiSnapshotData | null> {
  const id = projectId.trim()
  if (!id) return null
  try {
    const raw = await apiFetch<unknown>(`/analytics/projects/${encodeURIComponent(id)}/roi`, { method: "GET" })
    return parseRoiSnapshot(raw)
  } catch {
    return null
  }
}

/** GET /analytics/sessions/{session_id}/roi */
export async function fetchSessionRoiSnapshot(sessionId: string): Promise<RoiSnapshotData | null> {
  const id = sessionId.trim()
  if (!id) return null
  try {
    const raw = await apiFetch<unknown>(`/analytics/sessions/${encodeURIComponent(id)}/roi`, { method: "GET" })
    return parseRoiSnapshot(raw)
  } catch {
    return null
  }
}

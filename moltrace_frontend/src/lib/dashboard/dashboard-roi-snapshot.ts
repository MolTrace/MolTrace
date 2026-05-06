import { apiFetch } from "@/lib/api/client"
import { parseRoiSnapshot, type RoiSnapshotData } from "@/src/lib/analytics/roi-dashboard-data"

/** GET /analytics/roi — returns null if unavailable or unparsable (non-throwing). */
export async function fetchDashboardRoiSnapshot(): Promise<RoiSnapshotData | null> {
  try {
    const raw = await apiFetch<unknown>("/analytics/roi", { method: "GET" })
    return parseRoiSnapshot(raw)
  } catch {
    return null
  }
}

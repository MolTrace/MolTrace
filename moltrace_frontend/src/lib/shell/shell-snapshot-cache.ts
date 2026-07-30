/**
 * Cross-navigation snapshot cache for the app shell's providers.
 *
 * Why this exists
 * ---------------
 * Each app route renders `<AppShell>` from inside its own `page.tsx` rather than
 * from a shared layout, so a client-side navigation between two top-level
 * segments unmounts and remounts the entire shell — TenantProvider,
 * OverviewDataProvider and the topbar included. Their mount effects then re-run,
 * which meant every single tap on the mobile bottom nav kicked off the same
 * six-or-so workspace requests again (`/tenants`, `/projects`,
 * `/spectracheck/sessions`, `/jobs`, `/workflow-runs`,
 * `/ai/evidence-queue`) before the destination had anything to show. On a phone
 * that reads as "the nav lags".
 *
 * What it does
 * ------------
 * Keeps the last resolved value per key in module scope (so it survives the
 * remount, but not a full page load) and serves it synchronously. A remounted
 * provider therefore starts with real data instead of a loading state, and only
 * goes back to the network when the snapshot has aged past `maxAgeMs`.
 * Concurrent loads for one key share a single in-flight request.
 *
 * This is deliberately a cache, not a store: it never becomes the source of
 * truth. `invalidateShellSnapshots()` drops everything on the events that make
 * cached workspace data wrong — a tenant switch or an auth reset.
 */

type Snapshot<T> = {
  value: T
  /** `performance.now()` reading when `value` resolved. */
  at: number
}

const snapshots = new Map<string, Snapshot<unknown>>()
const inflight = new Map<string, Promise<unknown>>()

function now(): number {
  return typeof performance !== "undefined" && typeof performance.now === "function"
    ? performance.now()
    : Date.now()
}

/** Cached value for `key`, or `undefined` when absent. Never checks freshness. */
export function readShellSnapshot<T>(key: string): T | undefined {
  const entry = snapshots.get(key)
  return entry ? (entry.value as T) : undefined
}

/** True when `key` has a value that is still within `maxAgeMs`. */
export function isShellSnapshotFresh(key: string, maxAgeMs: number): boolean {
  const entry = snapshots.get(key)
  return entry != null && now() - entry.at <= maxAgeMs
}

export function writeShellSnapshot<T>(key: string, value: T): void {
  snapshots.set(key, { value, at: now() })
}

/**
 * Resolve `key`, reusing an in-flight load for the same key so two providers
 * mounting in the same commit issue one request rather than two.
 *
 * A rejected loader is NOT cached — the next caller retries.
 */
export function loadShellSnapshot<T>(key: string, loader: () => Promise<T>): Promise<T> {
  const existing = inflight.get(key)
  if (existing) return existing as Promise<T>

  const pending = loader()
    .then((value) => {
      writeShellSnapshot(key, value)
      return value
    })
    .finally(() => {
      inflight.delete(key)
    })

  inflight.set(key, pending)
  return pending
}

/**
 * Drop cached values. Pass a `keyPrefix` to scope the reset; omit it to clear
 * everything (tenant switch, sign-out, auth reset).
 */
export function invalidateShellSnapshots(keyPrefix?: string): void {
  if (!keyPrefix) {
    snapshots.clear()
    inflight.clear()
    return
  }
  for (const key of [...snapshots.keys()]) {
    if (key.startsWith(keyPrefix)) snapshots.delete(key)
  }
  for (const key of [...inflight.keys()]) {
    if (key.startsWith(keyPrefix)) inflight.delete(key)
  }
}

/** Keys used by the shell providers. Kept here so they cannot drift apart. */
export const SHELL_SNAPSHOT_KEYS = {
  tenantContext: "shell:tenant-context",
  overviewData: "shell:overview-data",
  aiEvidenceCount: "shell:ai-evidence-count",
  topbarNotifications: "shell:topbar-notifications",
} as const

/**
 * How long a snapshot is served without revalidating. Long enough that tapping
 * through the nav costs nothing, short enough that a workspace left open still
 * catches up on its own.
 */
export const SHELL_SNAPSHOT_MAX_AGE_MS = 30_000

import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  invalidateShellSnapshots,
  isShellSnapshotFresh,
  loadShellSnapshot,
  readShellSnapshot,
  SHELL_SNAPSHOT_KEYS,
  writeShellSnapshot,
} from "@/src/lib/shell/shell-snapshot-cache"

describe("shell snapshot cache", () => {
  beforeEach(() => {
    invalidateShellSnapshots()
  })

  it("serves a written value synchronously", () => {
    expect(readShellSnapshot<number>("k")).toBeUndefined()
    writeShellSnapshot("k", 42)
    expect(readShellSnapshot<number>("k")).toBe(42)
  })

  it("reports freshness against the requested max age", () => {
    writeShellSnapshot("k", "v")
    expect(isShellSnapshotFresh("k", 30_000)).toBe(true)
    // A zero-length window can still match a same-tick write, so assert on a
    // key that was never written instead of racing the clock.
    expect(isShellSnapshotFresh("missing", 30_000)).toBe(false)
  })

  it("shares one in-flight load between concurrent callers", async () => {
    // This is the case that fires on a route change: several shell providers
    // mount in the same commit and each asks for the same data.
    const loader = vi.fn(async () => "resolved")
    const [a, b, c] = await Promise.all([
      loadShellSnapshot("k", loader),
      loadShellSnapshot("k", loader),
      loadShellSnapshot("k", loader),
    ])

    expect(loader).toHaveBeenCalledTimes(1)
    expect([a, b, c]).toEqual(["resolved", "resolved", "resolved"])
    expect(readShellSnapshot<string>("k")).toBe("resolved")
  })

  it("does not cache a rejected load, so the next caller retries", async () => {
    const loader = vi
      .fn<() => Promise<string>>()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce("second try")

    await expect(loadShellSnapshot("k", loader)).rejects.toThrow("offline")
    expect(readShellSnapshot<string>("k")).toBeUndefined()

    await expect(loadShellSnapshot("k", loader)).resolves.toBe("second try")
    expect(loader).toHaveBeenCalledTimes(2)
  })

  it("clears only the matching prefix when one is given", () => {
    writeShellSnapshot(SHELL_SNAPSHOT_KEYS.tenantContext, "tenant")
    writeShellSnapshot(SHELL_SNAPSHOT_KEYS.overviewData, "overview")

    invalidateShellSnapshots(SHELL_SNAPSHOT_KEYS.tenantContext)

    expect(readShellSnapshot(SHELL_SNAPSHOT_KEYS.tenantContext)).toBeUndefined()
    expect(readShellSnapshot(SHELL_SNAPSHOT_KEYS.overviewData)).toBe("overview")
  })

  it("clears everything when no prefix is given (tenant switch / auth reset)", () => {
    writeShellSnapshot(SHELL_SNAPSHOT_KEYS.tenantContext, "tenant")
    writeShellSnapshot(SHELL_SNAPSHOT_KEYS.overviewData, "overview")
    writeShellSnapshot(SHELL_SNAPSHOT_KEYS.aiEvidenceCount, 3)

    invalidateShellSnapshots()

    for (const key of Object.values(SHELL_SNAPSHOT_KEYS)) {
      expect(readShellSnapshot(key)).toBeUndefined()
    }
  })
})

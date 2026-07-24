"use client"

/**
 * Repho Phase C — ML capability readout + SDL site status (developer-mode info panel).
 *
 * This is the honest face of the deliberately-unwired heavy paths: it explains why the
 * Generate/heavy-ML buttons don't exist on this deployment. It must never look like an error
 * state — absence of heavy extras is the designed default.
 */
import { useEffect, useState } from "react"
import { Cpu } from "lucide-react"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Badge } from "@/components/ui/badge"
import {
  getCapabilityReadout,
  getSdlStatus,
  parseCapabilityReadout,
  parseSdlSiteStatus,
  type CapabilityReadout,
  type SdlSiteStatus,
} from "@/lib/reaction/phase-c"

const CAPABILITY_LABEL: Record<string, string> = {
  forward_prediction: "Forward prediction (generative)",
  retrosynthesis: "Retrosynthesis route proposal",
  sdl_execution: "SDL execution (hardware automation)",
  yield_gnn: "Yield GNN (learned surrogate)",
}

export function MlCapabilitiesPanel() {
  const [readout, setReadout] = useState<CapabilityReadout | null>(null)
  const [sdl, setSdl] = useState<SdlSiteStatus | null>(null)
  const [err, setErr] = useState("")
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const [capRaw, sdlRaw] = await Promise.all([
          getCapabilityReadout(),
          getSdlStatus().catch(() => null),
        ])
        if (cancelled) return
        setReadout(parseCapabilityReadout(capRaw))
        setSdl(parseSdlSiteStatus(sdlRaw))
      } catch (e) {
        if (!cancelled) setErr(formatApiError(e, "Could not load the ML capability readout."))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <ModuleCard
      accent="slate"
      eyebrow="Developer · ML capabilities"
      title="Heavy-ML capability readout"
      icon={Cpu}
      description="What this deployment has actually enabled. Heavy generative paths (route proposal, forward generation, GNN training, SDL execution) are optional, default-off extras — their absence here is the designed state, not an error."
    >
      <div className="space-y-4 text-sm">
        {loading ? (
          <p className="text-xs text-muted-foreground">Loading capability readout…</p>
        ) : err ? (
          <p className="text-xs text-muted-foreground">{err}</p>
        ) : readout == null ? (
          <p className="text-xs text-muted-foreground">Capability readout unavailable.</p>
        ) : (
          <>
            <div className="space-y-2">
              {readout.capabilities.map((c) => (
                <div key={c.name} className="space-y-1 rounded-md border px-3 py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-xs font-medium text-foreground">
                      {CAPABILITY_LABEL[c.name] ?? c.name}
                    </p>
                    <Badge variant="outline" className="font-mono text-[10px]">
                      {c.name}
                    </Badge>
                    <Badge variant={c.available ? "default" : "outline"} className="text-[10px]">
                      {c.available ? "available" : "not installed"}
                    </Badge>
                    <Badge variant="outline" className="text-[10px]">
                      flag {c.enabled ? "on" : "off"}
                    </Badge>
                    {/* yield_gnn.active is false BY DESIGN even when flagged on: activation is
                        per-call via a benchmark-gate artifact, never a standing state. */}
                    <Badge variant="outline" className="text-[10px]">
                      {c.active
                        ? "active"
                        : c.name === "yield_gnn"
                          ? "inactive (per-call gate by design)"
                          : "inactive"}
                    </Badge>
                  </div>
                  {c.reason ? <p className="text-[11px] text-muted-foreground">{c.reason}</p> : null}
                  {c.missingModules.length > 0 ? (
                    <p className="text-[11px] text-muted-foreground">
                      missing modules:{" "}
                      <span className="font-mono text-foreground">{c.missingModules.join(", ")}</span>
                    </p>
                  ) : null}
                  {c.engine ? (
                    <p className="font-mono text-[10px] text-muted-foreground">{c.engine}</p>
                  ) : null}
                </div>
              ))}
            </div>
            {sdl != null ? (
              <div className="space-y-1 rounded-md border border-dashed px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-xs font-medium text-foreground">SDL site status</p>
                  <Badge variant="outline" className="text-[10px]">
                    {sdl.enabled ? "enabled" : "disabled"}
                  </Badge>
                  <Badge variant="secondary" className="text-[10px]">
                    execution surface: {sdl.executionSurfaceWired ? "wired" : "not wired"}
                  </Badge>
                </div>
                {sdl.detail ? <p className="text-[11px] text-muted-foreground">{sdl.detail}</p> : null}
                {sdl.disclaimer ? (
                  <p className="text-[11px] italic text-muted-foreground">{sdl.disclaimer}</p>
                ) : null}
              </div>
            ) : null}
            {readout.disclaimer ? (
              <p className="text-[11px] italic text-muted-foreground">{readout.disclaimer}</p>
            ) : null}
          </>
        )}
      </div>
    </ModuleCard>
  )
}

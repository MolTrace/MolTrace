import Link from "next/link"
import { Lock } from "lucide-react"

import { Button } from "@/components/ui/button"
import { readUpgradeRefusal, upgradeCopy } from "@/lib/api/upgrade-state"

/**
 * Renders one of the four closed-product states, or nothing.
 *
 * Returning null for anything that is not one of the four is deliberate: a caller
 * can drop this in beside its existing error handling without having to decide
 * first whether the failure was an entitlement one. If it is, this speaks; if it
 * is not, the caller's own message stands.
 *
 * There is no colour-coding by severity and no lock iconography beyond a single
 * neutral glyph. These are states of a commercial relationship, not faults —
 * dressing "your administrator has not enabled this yet" in warning red tells the
 * reader something untrue about whose problem it is.
 */
export function UpgradeNotice({ error, className }: { error: unknown; className?: string }) {
  const refusal = readUpgradeRefusal(error)
  if (!refusal) return null
  const copy = upgradeCopy(refusal)

  return (
    <div
      className={className}
      data-upgrade-state={refusal.state}
      role="status"
    >
      <div className="rounded-xl border bg-card p-5" style={{ borderLeftWidth: "3px", borderLeftColor: "var(--mt-amber)" }}>
        <div className="flex items-center gap-2">
          <Lock className="h-4 w-4 shrink-0" style={{ color: "var(--mt-amber)" }} aria-hidden />
          <h3 className="text-sm font-semibold" style={{ color: "var(--mt-amber-ink)" }}>
            {copy.title}
          </h3>
        </div>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{copy.body}</p>
        {copy.action ? (
          <Button variant="outline" size="sm" className="mt-4" asChild>
            <Link href={copy.action.href}>{copy.action.label}</Link>
          </Button>
        ) : null}
      </div>
    </div>
  )
}

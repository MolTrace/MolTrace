import { cn } from "@/lib/utils"
import { statusLabel, statusTone, type StatusTone } from "@/lib/ui/status"

// AA-safe soft fill + ink text per tone (info/pending use the --mt-*-ink tokens).
const TONE_CLASS: Record<StatusTone, string> = {
  success: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  danger: "border-red-500/50 bg-red-500/10 text-red-700 dark:text-red-300",
  warning: "border-amber-500/45 bg-amber-500/10 text-amber-800 dark:text-amber-300",
  info: "border-[color:var(--mt-cyan)]/40 bg-[color:var(--mt-cyan-soft)] text-[color:var(--mt-cyan-ink)]",
  pending: "border-[color:var(--mt-violet)]/40 bg-[color:var(--mt-violet-soft)] text-[color:var(--mt-violet-ink)]",
  neutral: "border-border bg-muted/60 text-muted-foreground",
}

/** A labeled, color-coded status pill — replaces raw status strings shown
 *  "as returned by the API". Empty status renders an em dash. */
export function StatusBadge({ status, className }: { status: unknown; className?: string }) {
  const raw = typeof status === "string" ? status.trim() : status == null ? "" : String(status)
  if (!raw) return <span className="text-muted-foreground">—</span>
  return (
    <span
      title={raw}
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium",
        TONE_CLASS[statusTone(raw)],
        className,
      )}
    >
      {statusLabel(raw)}
    </span>
  )
}

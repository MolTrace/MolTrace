"use client"

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ElementType,
  type ReactNode,
} from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { X, ChevronRight, RefreshCw } from "lucide-react"
import Link from "next/link"
import { useOptionalOverviewData } from "@/components/app/overview-data-context"
import {
  EvidenceCard,
  moduleLabel,
  type EvidenceRiskLevel,
  type EvidenceStatus,
} from "@/components/science/evidence-card"
import { StatusFilterPills } from "@/components/dashboard/status-filter-pills"
import { ApiError } from "@/lib/api/client"
import {
  AI_EVIDENCE_MODULE_HREFS,
  fetchAiEvidenceQueue,
  loadSharedAiEvidenceQueue,
  publishAiEvidenceQueue,
  type AIEvidenceItem,
  type AIEvidenceModule,
  type AIEvidenceReviewStatus,
  type AIEvidenceStatus,
} from "@/lib/api/ai-evidence"
import {
  isShellSnapshotFresh,
  loadShellSnapshot,
  readShellSnapshot,
  writeShellSnapshot,
  SHELL_SNAPSHOT_KEYS,
  SHELL_SNAPSHOT_MAX_AGE_MS,
} from "@/src/lib/shell/shell-snapshot-cache"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { toast } from "@/hooks/use-toast"
import { cn, formatStableUtcDateTime } from "@/lib/utils"
import { humanizeField, statusLabel } from "@/lib/ui/status"

type ReviewDialogState = {
  item: AIEvidenceItem
  status: Extract<AIEvidenceReviewStatus, "approved" | "rejected">
}

type ModuleFilter = "all" | AIEvidenceModule

function mapAiEvidenceStatus(status: AIEvidenceStatus): EvidenceStatus {
  if (status === "pending_review") return "pending_review"
  if (status === "approved") return "approved"
  if (status === "rejected") return "rejected"
  if (status === "contradiction") return "contradiction"
  return "draft"
}

function reviewErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401 || err.status === 403) return "You need access to review this evidence item."
    if (err.status === 404) return "This evidence item is no longer available for review."
    if (err.status === 422) return "Check the review comment and try again."
  }
  return "Could not save this review. Please try again."
}

/** Counts that are genuinely unknown stay null and print as an em dash: a reader
 *  must never read "0 needs review" when the real answer is "we couldn't check". */
function fmtCount(n: number | null | undefined): string {
  if (n == null) return "—"
  return String(n)
}

type PlatformRow = { label: string; value: number | null; href: string }

export type AIEvidenceQueuePanelProps = {
  onClose: () => void
  /** "docked" is the desktop right-hand slab; "sheet" fills a phone sheet. */
  variant?: "docked" | "sheet"
  /**
   * Element used for the panel heading. The sheet passes Radix's dialog title so
   * the dialog takes its accessible name from this one visible heading — adding a
   * second, hidden title would give the dialog two competing names.
   */
  titleAs?: ElementType<{ className?: string; children?: ReactNode }>
}

/**
 * Panel body, shared by the docked desktop panel and the mobile sheet.
 *
 * Beyond the review queue itself it always renders a platform-activity rollup.
 * The queue is frequently empty — that is the healthy state — and the panel used
 * to answer that with one sentence and 700px of blank space, which read as a
 * broken feature rather than a clear inbox.
 */
export function AIEvidenceQueuePanel({
  onClose,
  variant = "docked",
  titleAs: TitleTag = "h2",
}: AIEvidenceQueuePanelProps) {
  const overview = useOptionalOverviewData()
  const [items, setItems] = useState<AIEvidenceItem[]>(
    () => readShellSnapshot<AIEvidenceItem[]>(SHELL_SNAPSHOT_KEYS.aiEvidenceRows) ?? [],
  )
  // Seeded together with the rows: without this the panel would show its loading
  // state over data it already has, every time the shell remounts on navigation.
  const [loaded, setLoaded] = useState(
    () => readShellSnapshot<AIEvidenceItem[]>(SHELL_SNAPSHOT_KEYS.aiEvidenceRows) != null,
  )
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [moduleFilter, setModuleFilter] = useState<ModuleFilter>("all")
  const [reviewDialog, setReviewDialog] = useState<ReviewDialogState | null>(null)
  const [reviewComment, setReviewComment] = useState("")
  const [reviewBusy, setReviewBusy] = useState(false)
  const [reviewError, setReviewError] = useState("")

  const load = useCallback(async (force: boolean) => {
    if (!force && isShellSnapshotFresh(SHELL_SNAPSHOT_KEYS.aiEvidenceRows, SHELL_SNAPSHOT_MAX_AGE_MS)) {
      return
    }
    setLoading(true)
    try {
      const rows = force
        ? await fetchAiEvidenceQueue(100)
        : await loadSharedAiEvidenceQueue(loadShellSnapshot, SHELL_SNAPSHOT_KEYS.aiEvidenceRows)
      // A forced refresh bypasses the snapshot, so write the fresh answer back
      // and announce it — otherwise the topbar badge keeps serving the count it
      // was seeded with and visibly disagrees with the list right beside it.
      if (force) {
        writeShellSnapshot(SHELL_SNAPSHOT_KEYS.aiEvidenceRows, rows)
        publishAiEvidenceQueue(rows)
      }
      setItems(rows)
      setLoaded(true)
      setError("")
    } catch {
      setError("Review queue data is temporarily unavailable.")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(false)
  }, [load])

  const moduleCounts = useMemo(() => {
    const counts = { spectracheck: 0, regulatory: 0, reactions: 0, ai_services: 0 } as Record<
      AIEvidenceModule,
      number
    >
    for (const item of items) {
      if (item.module in counts) counts[item.module] += 1
    }
    return counts
  }, [items])

  const visibleItems = useMemo(
    () => (moduleFilter === "all" ? items : items.filter((item) => item.module === moduleFilter)),
    [items, moduleFilter],
  )

  const needsReviewCount = useMemo(
    () => items.filter((i) => i.status === "pending_review" || i.status === "contradiction").length,
    [items],
  )

  /* Platform activity, from data the surrounding provider already holds — no
     extra requests. Each figure stays null when its source did not load, so an
     unavailable list is never rendered as a zero. */
  const platformRows = useMemo((): PlatformRow[] => {
    const metrics = overview?.metrics ?? null
    const sessionsOk = overview?.sessionsDataAvailable === true
    const jobsOk = overview?.jobsDataAvailable === true
    const workflowsOk = overview?.workflowRunsDataAvailable === true
    const wf = overview?.workflowStatusSummary ?? null

    return [
      {
        label: "Analyses running",
        value: sessionsOk && metrics ? metrics.activeAnalyses : null,
        href: "/spectracheck",
      },
      {
        label: "Awaiting your review",
        value: sessionsOk && metrics ? metrics.reviewRequired : null,
        href: "/review",
      },
      {
        label: "Reports ready",
        value: sessionsOk && metrics ? metrics.reportsReady : null,
        href: "/reports",
      },
      {
        label: "Workflows running",
        value: workflowsOk && wf ? wf.active : null,
        href: "/dashboard",
      },
      {
        label: "Jobs failed",
        value: jobsOk && metrics && typeof metrics.jobsFailed === "number" ? metrics.jobsFailed : null,
        href: "/dashboard",
      },
    ]
  }, [overview])

  function openReview(item: AIEvidenceItem, status: ReviewDialogState["status"]) {
    setReviewDialog({ item, status })
    setReviewComment("")
    setReviewError("")
  }

  async function submitReview() {
    if (!reviewDialog) return
    setReviewBusy(true)
    setReviewError("")
    try {
      const { reviewAiEvidenceItem } = await import("@/lib/api/ai-evidence")
      const response = await reviewAiEvidenceItem(reviewDialog.item.id, {
        status: reviewDialog.status,
        review_comment: reviewComment.trim() || null,
      })
      setItems((prev) =>
        prev.map((item) => (item.id === response.evidence_item.id ? response.evidence_item : item)),
      )
      toast({
        title: reviewDialog.status === "approved" ? "Evidence approved" : "Evidence rejected",
        description: "Review status updated and recorded for audit.",
      })
      setReviewDialog(null)
      setReviewComment("")
      await load(true)
    } catch (err) {
      setReviewError(reviewErrorMessage(err))
    } finally {
      setReviewBusy(false)
    }
  }

  const footerLink =
    moduleFilter === "all"
      ? { href: "/spectracheck", label: "View All Analyses" }
      : {
          href: AI_EVIDENCE_MODULE_HREFS[moduleFilter],
          label: `Open ${moduleLabel(moduleFilter)}`,
        }

  const reviewActionLabel = reviewDialog?.status === "approved" ? "Approve" : "Reject"
  const showEmptyQueue = loaded && !loading && items.length === 0
  const showFilteredEmpty = loaded && !loading && items.length > 0 && visibleItems.length === 0

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 border-b px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <TitleTag className="truncate font-semibold">AI Evidence Queue</TitleTag>
          <Badge variant="secondary">{loaded ? items.length : "—"}</Badge>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => void load(true)}
            disabled={loading}
            aria-label="Refresh AI Evidence Queue"
          >
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} aria-hidden />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={onClose}
            aria-label="Close AI Evidence Queue"
          >
            <X className="h-4 w-4" aria-hidden />
          </Button>
        </div>
      </div>

      {error ? <p className="border-b px-4 py-1.5 text-[11px] text-muted-foreground">{error}</p> : null}

      {loaded && items.length > 0 ? (
        <div className="border-b px-3 py-2">
          <StatusFilterPills
            label="Filter evidence by module"
            value={moduleFilter}
            onChange={setModuleFilter}
            options={[
              { value: "all", label: "All", count: items.length },
              { value: "spectracheck", label: "SpectraCheck", count: moduleCounts.spectracheck },
              { value: "regulatory", label: "Regentry", count: moduleCounts.regulatory },
              { value: "reactions", label: "Reactions", count: moduleCounts.reactions },
              { value: "ai_services", label: "AI Services", count: moduleCounts.ai_services },
            ]}
          />
          {needsReviewCount > 0 ? (
            <p className="mt-2 text-[11px] text-muted-foreground">
              {needsReviewCount} {needsReviewCount === 1 ? "item needs" : "items need"} your review.
            </p>
          ) : null}
        </div>
      ) : null}

      <div className={cn("min-h-0 flex-1 overflow-y-auto p-3", variant === "sheet" && "pb-6")}>
        <div className="space-y-3">
          {loading && !loaded ? (
            <p className="px-1 text-xs text-muted-foreground">Loading review queue…</p>
          ) : null}

          {showEmptyQueue ? (
            <div className="rounded-md border bg-muted/20 px-3 py-3">
              <p className="text-xs font-medium">Nothing waiting on you here</p>
              <p className="mt-1 text-[11px] text-muted-foreground">
                No AI findings are queued for review. Here&apos;s what else is moving across the
                platform.
              </p>
            </div>
          ) : null}

          {showFilteredEmpty ? (
            <p className="px-1 text-xs text-muted-foreground">
              No evidence from {moduleLabel(moduleFilter as AIEvidenceModule)} right now.
            </p>
          ) : null}

          {visibleItems.map((item) => (
            <EvidenceCard
              key={item.id}
              compact
              title={`Evidence ${item.id}`}
              module={item.module}
              status={mapAiEvidenceStatus(item.status)}
              confidence_score={item.confidence_score}
              confidence_label={item.status === "pending_review" ? "needs review" : statusLabel(item.status)}
              risk_level={item.risk_level as EvidenceRiskLevel}
              summary={item.summary || "Evidence summary unavailable."}
              evidence_items={[
                `Record: ${humanizeField(item.entity_type)} ${item.entity_id}`,
                `Updated: ${formatStableUtcDateTime(item.updated_at)}`,
              ]}
              citations={[]}
              // No reviewer name is carried on a queued item, and the numeric id
              // that is carried is a storage row number — meaningless to a reader.
              review_status={item.reviewed_at ? statusLabel(item.status) : "awaiting review"}
              onApprove={() => openReview(item, "approved")}
              onReject={() => openReview(item, "rejected")}
              className="transition-shadow hover:shadow-md"
            />
          ))}

          {/* Always present, queue empty or not: this is the panel's answer to
              "what is happening across the platform right now". */}
          <div className="rounded-md border">
            <p className="border-b px-3 py-2 font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
              Platform activity
            </p>
            <ul className="divide-y">
              {platformRows.map((row) => (
                <li key={row.label}>
                  <Link
                    href={row.href}
                    className="flex min-h-11 items-center justify-between gap-3 px-3 py-2 text-xs transition-colors hover:bg-muted/40"
                  >
                    <span className="min-w-0 truncate text-muted-foreground">{row.label}</span>
                    <span className="shrink-0 font-mono text-sm font-bold tabular-nums">
                      {fmtCount(row.value)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
            {overview == null ? (
              <p className="border-t px-3 py-2 text-[11px] text-muted-foreground">
                Platform activity is only available inside the workspace.
              </p>
            ) : null}
          </div>
        </div>
      </div>

      {/* `env()` resolves to 0 where it is unsupported, and the 0.75rem keeps the
          padding sane there, so no fallback declaration is needed. */}
      <div className="border-t p-3 pb-[calc(env(safe-area-inset-bottom)+0.75rem)]">
        <Button variant="outline" className="w-full justify-between" asChild>
          {/* Follows the filter: sending someone filtered to Regentry off to
              SpectraCheck is a dead end. */}
          <Link href={footerLink.href}>
            {footerLink.label}
            <ChevronRight className="h-4 w-4" aria-hidden />
          </Link>
        </Button>
      </div>

      <Dialog
        open={reviewDialog != null}
        onOpenChange={(open) => {
          if (!open && !reviewBusy) {
            setReviewDialog(null)
            setReviewError("")
          }
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{reviewActionLabel} evidence</DialogTitle>
            <DialogDescription className="line-clamp-2">
              {reviewDialog?.item.summary || "Confirm the evidence review action."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-100">
              This action will be recorded in the audit trail.
            </p>
            <div className="space-y-1.5">
              <Label htmlFor="ai-evidence-review-comment" className="text-xs">
                Review comment
              </Label>
              <Textarea
                id="ai-evidence-review-comment"
                value={reviewComment}
                onChange={(event) => setReviewComment(event.target.value)}
                rows={3}
                placeholder="Optional reviewer note"
              />
            </div>
            {reviewError ? <p className="text-xs text-destructive">{reviewError}</p> : null}
          </div>
          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button
              type="button"
              variant="outline"
              disabled={reviewBusy}
              onClick={() => {
                setReviewDialog(null)
                setReviewError("")
              }}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant={reviewDialog?.status === "rejected" ? "destructive" : "default"}
              disabled={reviewBusy}
              onClick={() => void submitReview()}
            >
              {reviewBusy ? "Saving…" : reviewActionLabel}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

/**
 * The docked desktop column.
 *
 * An ordinary flex sibling of `<main>` rather than a fixed overlay. The overlay
 * version had to hard-code where the topbar ended (`top-14`) and derive its own
 * height from `100vh` — the first breaks whenever anything above the shell adds
 * height (the offline banner does exactly that), and the second is measured
 * against the wrong box by mobile Safari. Neither guess is needed here.
 *
 * `hidden lg:flex` keeps the breakpoint in CSS: below lg the sheet takes over,
 * and no JavaScript has to settle before the correct surface paints.
 */
export function AIEvidenceQueue({ onClose }: { onClose: () => void }) {
  return (
    <aside
      aria-label="AI Evidence Queue"
      className="hidden w-80 shrink-0 overflow-hidden border-l bg-background lg:flex lg:flex-col"
    >
      <AIEvidenceQueuePanel onClose={onClose} variant="docked" />
    </aside>
  )
}

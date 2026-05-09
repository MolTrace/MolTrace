"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { X, ChevronRight } from "lucide-react"
import Link from "next/link"
import { useOptionalOverviewData } from "@/components/app/overview-data-context"
import { EvidenceCard, type EvidenceRiskLevel, type EvidenceStatus } from "@/components/science/evidence-card"
import { ApiError } from "@/lib/api/client"
import {
  fetchAiEvidenceQueue,
  reviewAiEvidenceItem,
  type AIEvidenceItem,
  type AIEvidenceModule,
  type AIEvidenceReviewStatus,
  type AIEvidenceStatus,
} from "@/lib/api/ai-evidence"
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

const DEMO_QUEUE_ITEMS = [
  {
    id: "NMR-2024-0847",
    type: "NMR Structure",
    confidence: 87,
    status: "contradiction" as const,
    project: "API-2024-Q4",
    timeAgo: "12 min ago",
  },
  {
    id: "MSMS-2024-1293",
    type: "MS/MS Annotation",
    confidence: 92,
    status: "high_confidence" as const,
    project: "Metabolite Study",
    timeAgo: "24 min ago",
  },
  {
    id: "RXN-OPT-2024-156",
    type: "Reaction Optimization",
    confidence: 78,
    status: "pending" as const,
    project: "Process Dev",
    timeAgo: "1 hr ago",
  },
]

type QueueItem = {
  id: string
  type: string
  confidence: number
  status: "contradiction" | "high_confidence" | "pending"
  project: string
  timeAgo: string
}

interface AIEvidenceQueueProps {
  onClose: () => void
}

type ReviewDialogState = {
  item: AIEvidenceItem
  status: Extract<AIEvidenceReviewStatus, "approved" | "rejected">
}

function mapQueueStatus(status: QueueItem["status"]): EvidenceStatus {
  if (status === "contradiction") return "contradiction"
  if (status === "pending") return "pending_review"
  return "draft"
}

function mapAiEvidenceStatus(status: AIEvidenceStatus): EvidenceStatus {
  if (status === "pending_review") return "pending_review"
  if (status === "approved") return "approved"
  if (status === "rejected") return "rejected"
  if (status === "contradiction") return "contradiction"
  return "draft"
}

function mapAiEvidenceModule(module: AIEvidenceModule) {
  return module
}

function mapQueueRisk(status: QueueItem["status"]): EvidenceRiskLevel {
  if (status === "contradiction") return "high"
  if (status === "pending") return "medium"
  return "low"
}

function queueConfidenceLabel(status: QueueItem["status"]): string {
  if (status === "high_confidence") return "high estimate"
  if (status === "contradiction") return "conflicting"
  return "needs review"
}

function reviewErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401 || err.status === 403) return "You need access to review this evidence item."
    if (err.status === 404) return "This evidence item is no longer available for review."
    if (err.status === 422) return "Check the review comment and try again."
  }
  return "Could not save this review. Please try again."
}

export function AIEvidenceQueue({ onClose }: AIEvidenceQueueProps) {
  const overview = useOptionalOverviewData()
  const [aiEvidenceItems, setAiEvidenceItems] = useState<AIEvidenceItem[]>([])
  const [aiEvidenceLoaded, setAiEvidenceLoaded] = useState(false)
  const [aiEvidenceLoading, setAiEvidenceLoading] = useState(false)
  const [aiEvidenceError, setAiEvidenceError] = useState("")
  const [reviewDialog, setReviewDialog] = useState<ReviewDialogState | null>(null)
  const [reviewComment, setReviewComment] = useState("")
  const [reviewBusy, setReviewBusy] = useState(false)
  const [reviewError, setReviewError] = useState("")

  const loading = overview?.loading === true
  const sessionsOk = overview?.sessionsDataAvailable === true

  const loadAiEvidenceQueue = useCallback(async () => {
    setAiEvidenceLoading(true)
    try {
      const rows = await fetchAiEvidenceQueue()
      setAiEvidenceItems(rows)
      setAiEvidenceLoaded(true)
      setAiEvidenceError("")
    } catch {
      setAiEvidenceError("AI evidence review data is temporarily unavailable.")
    } finally {
      setAiEvidenceLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadAiEvidenceQueue()
  }, [loadAiEvidenceQueue])

  const fallbackQueueItems = useMemo((): QueueItem[] => {
    if (loading || !overview) return DEMO_QUEUE_ITEMS
    if (sessionsOk) return overview.evidenceQueue ?? []
    return DEMO_QUEUE_ITEMS
  }, [loading, overview, sessionsOk])

  const fallbackBadgeCount =
    loading || !overview
      ? DEMO_QUEUE_ITEMS.length
      : sessionsOk && overview.metrics != null
        ? overview.metrics.evidenceQueue
        : DEMO_QUEUE_ITEMS.length

  const badgeCount = aiEvidenceLoaded ? aiEvidenceItems.length : fallbackBadgeCount
  const showDemoFallback = !aiEvidenceLoaded && !loading && overview != null && !sessionsOk
  const showBackendFallbackNotice = !aiEvidenceLoaded && Boolean(aiEvidenceError)
  const showBackendRefreshNotice = aiEvidenceLoaded && Boolean(aiEvidenceError)

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
      const response = await reviewAiEvidenceItem(reviewDialog.item.id, {
        status: reviewDialog.status,
        review_comment: reviewComment.trim() || null,
      })
      setAiEvidenceItems((prev) =>
        prev.map((item) => (item.id === response.evidence_item.id ? response.evidence_item : item)),
      )
      toast({
        title: reviewDialog.status === "approved" ? "Evidence approved" : "Evidence rejected",
        description: "Review status updated and recorded for audit.",
      })
      setReviewDialog(null)
      setReviewComment("")
      await loadAiEvidenceQueue()
    } catch (err) {
      setReviewError(reviewErrorMessage(err))
    } finally {
      setReviewBusy(false)
    }
  }

  const reviewActionLabel = reviewDialog?.status === "approved" ? "Approve" : "Reject"

  return (
    <aside className="fixed right-0 top-14 hidden h-[calc(100vh-3.5rem)] w-80 border-l bg-background lg:block">
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <h2 className="font-semibold">AI Evidence Queue</h2>
            <Badge variant="secondary">{badgeCount}</Badge>
          </div>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        {showDemoFallback ? (
          <p className="border-b px-4 py-1.5 text-[10px] text-muted-foreground">Demo queue</p>
        ) : null}
        {showBackendFallbackNotice ? (
          <p className="border-b px-4 py-1.5 text-[10px] text-muted-foreground">{aiEvidenceError}</p>
        ) : null}
        {showBackendRefreshNotice ? (
          <p className="border-b px-4 py-1.5 text-[10px] text-muted-foreground">{aiEvidenceError}</p>
        ) : null}

        <div className="flex-1 overflow-y-auto p-3">
          <div className="space-y-3">
            {aiEvidenceLoading && !aiEvidenceLoaded ? (
              <p className="px-1 text-xs text-muted-foreground">Loading review queue…</p>
            ) : null}
            {aiEvidenceLoaded && !aiEvidenceLoading && aiEvidenceItems.length === 0 ? (
              <p className="px-1 text-xs text-muted-foreground">No AI evidence items are queued.</p>
            ) : null}
            {!aiEvidenceLoaded && sessionsOk && !loading && fallbackQueueItems.length === 0 ? (
              <p className="px-1 text-xs text-muted-foreground">No flagged sessions.</p>
            ) : null}
            {aiEvidenceLoaded
              ? aiEvidenceItems.map((item) => (
                  <EvidenceCard
                    key={item.id}
                    compact
                    title={`Evidence ${item.id}`}
                    module={mapAiEvidenceModule(item.module)}
                    status={mapAiEvidenceStatus(item.status)}
                    confidence_score={item.confidence_score}
                    confidence_label={item.status === "pending_review" ? "needs review" : item.status.replace(/_/g, " ")}
                    risk_level={item.risk_level}
                    summary={item.summary || "Evidence summary unavailable."}
                    evidence_items={[
                      `Entity: ${item.entity_type} ${item.entity_id}`,
                      `Updated: ${item.updated_at}`,
                    ]}
                    citations={[]}
                    reviewer_name={item.reviewer_id != null ? `Reviewer ${item.reviewer_id}` : undefined}
                    review_status={item.reviewed_at ? item.status : "awaiting review"}
                    onApprove={() => openReview(item, "approved")}
                    onReject={() => openReview(item, "rejected")}
                    className="transition-shadow hover:shadow-md"
                  />
                ))
              : fallbackQueueItems.map((item) => (
                  <EvidenceCard
                    key={item.id}
                    compact
                    title={item.id}
                    module="spectracheck"
                    status={mapQueueStatus(item.status)}
                    confidence_score={item.confidence}
                    confidence_label={queueConfidenceLabel(item.status)}
                    risk_level={mapQueueRisk(item.status)}
                    summary={item.type}
                    evidence_items={[`Project: ${item.project}`, `Updated: ${item.timeAgo}`]}
                    citations={[]}
                    review_status={item.status === "pending" ? "triage pending" : undefined}
                    className="transition-shadow hover:shadow-md"
                  />
                ))}
          </div>
        </div>

        <div className="border-t p-3">
          <Button variant="outline" className="w-full justify-between" asChild>
            <Link href="/spectracheck">
              View All Analyses
              <ChevronRight className="h-4 w-4" />
            </Link>
          </Button>
        </div>
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
    </aside>
  )
}

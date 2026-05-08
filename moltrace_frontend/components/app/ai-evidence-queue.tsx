"use client"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { X, ChevronRight } from "lucide-react"
import Link from "next/link"
import { useOptionalOverviewData } from "@/components/app/overview-data-context"
import { EvidenceCard, type EvidenceRiskLevel, type EvidenceStatus } from "@/components/science/evidence-card"

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

function mapQueueStatus(status: QueueItem["status"]): EvidenceStatus {
  if (status === "contradiction") return "contradiction"
  if (status === "pending") return "pending_review"
  return "draft"
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

export function AIEvidenceQueue({ onClose }: AIEvidenceQueueProps) {
  const overview = useOptionalOverviewData()

  const loading = overview?.loading === true
  const sessionsOk = overview?.sessionsDataAvailable === true

  const queueItems =
    loading || !overview
      ? DEMO_QUEUE_ITEMS
      : sessionsOk
        ? overview.evidenceQueue ?? []
        : DEMO_QUEUE_ITEMS

  const badgeCount =
    loading || !overview
      ? DEMO_QUEUE_ITEMS.length
      : sessionsOk && overview.metrics != null
        ? overview.metrics.evidenceQueue
        : DEMO_QUEUE_ITEMS.length

  const showDemoFallback = !loading && overview != null && !sessionsOk

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

        <div className="flex-1 overflow-y-auto p-3">
          <div className="space-y-3">
            {sessionsOk && !loading && queueItems.length === 0 ? (
              <p className="px-1 text-xs text-muted-foreground">No flagged sessions.</p>
            ) : null}
            {(queueItems as QueueItem[]).map((item) => (
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
    </aside>
  )
}

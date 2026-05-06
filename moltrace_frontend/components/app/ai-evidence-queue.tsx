"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { X, AlertTriangle, CheckCircle2, Clock, ChevronRight } from "lucide-react"
import Link from "next/link"
import { useOptionalOverviewData } from "@/components/app/overview-data-context"

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

interface AIEvidenceQueueProps {
  onClose: () => void
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
            {queueItems.map((item) => (
              <Card key={item.id} className="cursor-pointer transition-shadow hover:shadow-md">
                <CardHeader className="p-3 pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <CardTitle className="text-sm font-medium">{item.id}</CardTitle>
                      <p className="text-xs text-muted-foreground">{item.type}</p>
                    </div>
                    {item.status === "contradiction" && (
                      <Badge variant="outline" className="gap-1 border-warning/50 text-warning">
                        <AlertTriangle className="h-3 w-3" />
                        Contradiction
                      </Badge>
                    )}
                    {item.status === "high_confidence" && (
                      <Badge variant="outline" className="gap-1 border-success/50 text-success">
                        <CheckCircle2 className="h-3 w-3" />
                        High
                      </Badge>
                    )}
                    {item.status === "pending" && (
                      <Badge variant="outline" className="gap-1">
                        <Clock className="h-3 w-3" />
                        Pending
                      </Badge>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="p-3 pt-0">
                  <div className="mb-2 flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">Confidence</span>
                    <span className="font-mono font-medium">{item.confidence}%</span>
                  </div>
                  <Progress value={item.confidence} className="h-1.5" />
                  <div className="mt-3 flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">{item.project}</span>
                    <span className="text-xs text-muted-foreground">{item.timeAgo}</span>
                  </div>
                </CardContent>
              </Card>
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

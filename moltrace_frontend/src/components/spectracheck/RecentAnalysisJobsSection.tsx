"use client"

import { useEffect } from "react"
import { History } from "lucide-react"
import { AnalysisJobTimeline } from "@/src/components/spectracheck/AnalysisJobTimeline"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { useAnalysisJob } from "@/src/lib/spectracheck/useAnalysisJob"

function RecentJobPanel({ jobId }: { jobId: string }) {
  const job = useAnalysisJob()
  const { pollJob } = job
  useEffect(() => {
    void pollJob(jobId)
  }, [jobId, pollJob])
  return (
    <AnalysisJobTimeline
      job={job}
      variant="compact"
      evidenceLayer="report"
      sourceTab="Recent Analysis Jobs"
    />
  )
}

export function RecentAnalysisJobsSection({ jobIds }: { jobIds: readonly string[] }) {
  return (
    <Card className="min-w-0">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Recent Analysis Jobs</CardTitle>
        <CardDescription>
          Jobs started from Overview or upload tabs during this session. Status polls automatically until completion.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {jobIds.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <History />
              </EmptyMedia>
              <EmptyTitle>No analysis jobs yet</EmptyTitle>
              <EmptyDescription>
                Jobs you start from Overview or the upload tabs will appear here and poll
                automatically until they complete.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          jobIds.map((id) => <RecentJobPanel key={id} jobId={id} />)
        )}
      </CardContent>
    </Card>
  )
}

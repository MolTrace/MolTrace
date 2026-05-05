"use client"

import { useEffect } from "react"
import { AnalysisJobTimeline } from "@/src/components/spectracheck/AnalysisJobTimeline"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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
          <p className="text-sm text-muted-foreground">No analysis jobs started yet.</p>
        ) : (
          jobIds.map((id) => <RecentJobPanel key={id} jobId={id} />)
        )}
      </CardContent>
    </Card>
  )
}

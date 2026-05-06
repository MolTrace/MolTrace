import { AppShell } from "@/components/app/app-shell"
import { RegulatorySourceVersionTimelineWorkspace } from "@/components/regulatory-hub/regulatory-source-version-timeline-workspace"

export default async function RegulatorySourceVersionPage({
  params,
}: {
  params: Promise<{ sourceId: string }>
}) {
  const p = await params
  const sourceIdNum = Number.parseInt(p.sourceId, 10)
  return (
    <AppShell>
      <RegulatorySourceVersionTimelineWorkspace sourceId={sourceIdNum} />
    </AppShell>
  )
}

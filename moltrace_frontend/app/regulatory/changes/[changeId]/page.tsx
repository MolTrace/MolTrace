import { AppShell } from "@/components/app/app-shell"
import { RegulatoryChangeDetailWorkspace } from "@/components/regulatory-hub/regulatory-change-detail-workspace"

export default async function RegulatoryChangeDetailPage({
  params,
}: {
  params: Promise<{ changeId: string }>
}) {
  const p = await params
  const changeIdNum = Number.parseInt(p.changeId, 10)
  return (
    <AppShell>
      <RegulatoryChangeDetailWorkspace changeId={changeIdNum} />
    </AppShell>
  )
}

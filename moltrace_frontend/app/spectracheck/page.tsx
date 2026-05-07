import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { ProgramsInterfaceWorkspace } from "@/components/programs/programs-interface-workspace"

export default function SpectraCheckPage({
  searchParams,
}: {
  searchParams?: { [key: string]: string | string[] | undefined }
}) {
  const desktopMode = searchParams?.desktop === "1"
  const sessionIdParam = searchParams?.sessionId
  const sessionId = typeof sessionIdParam === "string" ? sessionIdParam : null
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading SpectraCheck…</div>}>
        <ProgramsInterfaceWorkspace desktopMode={desktopMode} sessionId={sessionId} />
      </Suspense>
    </AppShell>
  )
}

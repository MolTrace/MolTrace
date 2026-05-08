import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { ProgramsInterfaceWorkspace } from "@/components/programs/programs-interface-workspace"

export default async function SpectraCheckPage({
  searchParams,
}: {
  searchParams?: Promise<{ [key: string]: string | string[] | undefined }>
}) {
  const resolvedSearchParams = searchParams ? await searchParams : undefined
  const desktopMode = resolvedSearchParams?.desktop === "1"
  const sessionIdParam = resolvedSearchParams?.sessionId
  const sessionId = typeof sessionIdParam === "string" ? sessionIdParam : null
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading SpectraCheck…</div>}>
        <ProgramsInterfaceWorkspace desktopMode={desktopMode} sessionId={sessionId} />
      </Suspense>
    </AppShell>
  )
}

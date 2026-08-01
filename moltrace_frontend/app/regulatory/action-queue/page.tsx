import { Suspense } from "react"
import Link from "next/link"
import { AppShell } from "@/components/app/app-shell"
import { RegentryModuleNav } from "@/components/regulatory-hub/regentry-module-nav"
import {
  ACTION_QUEUE_TOOLTIP,
  RegulatoryActionQueue,
} from "@/components/regulatory-hub/regulatory-action-queue"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function RegulatoryActionQueuePage() {
  return (
    <AppShell>
      <RegentryModuleNav />
      <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">Loading…</p>}>
        <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle className="text-lg">Regulatory Action Queue</CardTitle>
                <InfoTooltip label="Regulatory action queue" content={ACTION_QUEUE_TOOLTIP} />
              </div>
              <CardDescription>
                Review, assign, and resolve regulatory action items across every dossier. Dossier context:{" "}
                <Link href="/regulatory" className="underline-offset-4 hover:underline">
                  Regulatory home
                </Link>
                .
              </CardDescription>
            </CardHeader>
            <CardContent>
              <RegulatoryActionQueue />
            </CardContent>
          </Card>
        </div>
      </Suspense>
    </AppShell>
  )
}

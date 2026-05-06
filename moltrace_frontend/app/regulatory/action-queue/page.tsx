import { Suspense } from "react"
import Link from "next/link"
import { AppShell } from "@/components/app/app-shell"
import {
  ACTION_QUEUE_TOOLTIP,
  RegulatoryActionQueue,
} from "@/components/regulatory-hub/regulatory-action-queue"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function RegulatoryActionQueuePage() {
  return (
    <AppShell>
      <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">Loading…</p>}>
        <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
          <div className="flex flex-wrap gap-2">
            <Link
              href="/regulatory/surveillance"
              className="inline-flex h-8 items-center rounded-md border px-3 text-sm hover:bg-accent"
            >
              Surveillance dashboard
            </Link>
            <Link
              href="/regulatory/rule-updates"
              className="inline-flex h-8 items-center rounded-md border px-3 text-sm hover:bg-accent"
            >
              Rule update proposals
            </Link>
            <Link
              href="/regulatory/sources"
              className="inline-flex h-8 items-center rounded-md border px-3 text-sm hover:bg-accent"
            >
              Source library
            </Link>
          </div>
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle className="text-lg">Regulatory Action Queue</CardTitle>
                <InfoTooltip label="Regulatory action queue" content={ACTION_QUEUE_TOOLTIP} />
              </div>
              <CardDescription>
                GET /regulatory/action-items · PATCH /regulatory/action-items/{"{action_item_id}"} · POST
                /regulatory/action-items. Dossier context:{" "}
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

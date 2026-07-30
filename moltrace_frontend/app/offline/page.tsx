import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function OfflinePage() {
  return (
    <main className="min-h-[70vh] px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-2xl">
        <Card className="border-muted">
          <CardHeader>
            <CardTitle>You&rsquo;re offline</CardTitle>
            <CardDescription>MolTrace can&rsquo;t be reached right now.</CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            You can still review draft actions saved on this device. Spectral analysis and report
            generation need a connection and will work again once you&rsquo;re back online.
          </CardContent>
        </Card>
      </div>
    </main>
  )
}

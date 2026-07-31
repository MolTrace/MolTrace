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
            Draft actions saved on this device are still readable. Spectral analysis and report
            generation resume when you reconnect.
          </CardContent>
        </Card>
      </div>
    </main>
  )
}

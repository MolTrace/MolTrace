import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function OfflinePage() {
  return (
    <main className="min-h-[70vh] px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-2xl">
        <Card className="border-muted">
          <CardHeader>
            <CardTitle>Offline</CardTitle>
            <CardDescription>Connection to MolTrace services is currently unavailable.</CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            You are offline. You can review locally saved draft actions, but scientific analysis and report generation
            require backend connection.
          </CardContent>
        </Card>
      </div>
    </main>
  )
}

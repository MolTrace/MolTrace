"use client"

import { useState } from "react"
import { CheckCircle2, FileJson } from "lucide-react"
import { AppShell } from "@/components/app/app-shell"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { apiFetch } from "@/lib/api/client"

export default function ApiTestPage() {
  const [result, setResult] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  async function testBackend() {
    setLoading(true)
    setError("")
    setResult("")

    try {
      const data = await apiFetch<unknown>("/openapi.json")
      setResult(JSON.stringify(data, null, 2).slice(0, 5000))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backend connection failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <AppShell>
      <div className="mx-auto min-w-0 max-w-6xl space-y-6">
        <div>
          <Badge variant="outline">Development check</Badge>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight">
            Frontend → Next.js Proxy → FastAPI Backend
          </h1>
          <p className="text-muted-foreground">
            Verifies that browser code calls the Next.js proxy instead of the backend directly.
          </p>
        </div>

        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Backend connection</CardTitle>
            <CardDescription>
              Calls <code>/api/backend/openapi.json</code> through the shared API client.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button
              type="button"
              onClick={testBackend}
              disabled={loading}
              className="w-full sm:w-auto"
            >
              {loading ? "Testing..." : "Test backend connection"}
            </Button>

            {error && (
              <div className="rounded-md border border-warning/40 bg-warning/10 p-4 text-sm text-warning">
                {error}
              </div>
            )}

            {result && !error && (
              <div className="flex flex-wrap items-center gap-2 rounded-md border border-success/30 bg-success/5 px-3 py-2 text-sm">
                <CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />
                <span className="font-medium">Proxy reachable — OpenAPI payload received.</span>
              </div>
            )}

            {result && (
              <details className="rounded-lg border bg-card p-4">
                <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium">
                  <FileJson className="h-4 w-4" />
                  Developer JSON (preview)
                </summary>
                <pre className="mt-4 max-h-[560px] overflow-x-auto overflow-y-auto whitespace-pre-wrap rounded-md bg-muted/40 p-4 text-xs leading-5">
                  {result}
                </pre>
              </details>
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  )
}

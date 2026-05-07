"use client"

import { useState } from "react"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ValidationTraceabilityMatrixPanel } from "@/components/validation/validation-traceability-matrix-panel"

export function ValidationTraceabilityWorkspace() {
  const [projectIdInput, setProjectIdInput] = useState("")
  const [validationProjectId, setValidationProjectId] = useState("")

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Traceability Matrix</h1>
          <p className="text-muted-foreground">
            Traceability maps user requirements to functions, risks, test cases, execution evidence, and validation coverage gaps.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Validation project</CardTitle>
          <CardDescription>Enter a validation project id to load or generate its traceability matrix.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
            <div className="space-y-1">
              <Label htmlFor="traceability-validation-project-id">validation project ID</Label>
              <Input
                id="traceability-validation-project-id"
                value={projectIdInput}
                onChange={(event) => setProjectIdInput(event.target.value)}
              />
            </div>
            <Button type="button" onClick={() => setValidationProjectId(projectIdInput.trim())}>
              Load traceability matrix
            </Button>
          </div>
        </CardContent>
      </Card>

      {validationProjectId ? (
        <ValidationTraceabilityMatrixPanel validationProjectId={validationProjectId} />
      ) : null}
    </div>
  )
}

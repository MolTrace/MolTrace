"use client"

import { useState } from "react"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ModuleCard } from "@/components/dashboard/module-card"
import { ValidationTraceabilityMatrixPanel } from "@/components/validation/validation-traceability-matrix-panel"
import { Network } from "lucide-react"

export function ValidationTraceabilityWorkspace() {
  const [projectIdInput, setProjectIdInput] = useState("")
  const [validationProjectId, setValidationProjectId] = useState("")

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-cyan)" }}
          >
            MolTrace · Traceability Matrix
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Traceability Matrix</h1>
          <p className="text-sm text-muted-foreground">
            Traceability maps user requirements to functions, risks, test cases, execution evidence, and validation coverage gaps.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      <ModuleCard
        accent="cyan"
        eyebrow="Project"
        title="Validation project"
        icon={Network}
        description="Enter a validation project id to load or generate its traceability matrix."
      >
        <div className="space-y-3">
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
        </div>
      </ModuleCard>

      {validationProjectId ? (
        <ValidationTraceabilityMatrixPanel validationProjectId={validationProjectId} />
      ) : null}
    </div>
  )
}

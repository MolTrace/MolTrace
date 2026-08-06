"use client"

// Golden Path — expected-output contract results.
//
// This is the honest substitute for a "✓ it worked" claim: each contract the
// scenario defines, checked against what the arc's endpoints ACTUALLY returned.
//
// Why the check runs here and not on the server:
// `POST /pilot/runs/{id}/validate` reads `PilotRunStep.output_summary_json`, and
// the only route that writes those steps fills them with canned literals
// (`expected_output: "safe summary"`). Nothing writes a real step output back,
// so a server-side `pass` would be a statement about a hardcoded string. The
// contract semantics are identical either way — see `evaluateContracts` — so the
// same contracts are applied to the real responses instead, and the panel says
// plainly which artefact was checked.

import { AlertTriangle, CheckCircle2, CircleDashed, XCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { humanizeField } from "@/lib/ui/status"
import { GOLDEN_PATH_STEPS, type ContractCheck, type ContractCheckStatus } from "@/lib/pilot/golden-path"

const STATUS_PRESENTATION: Record<
  ContractCheckStatus,
  { label: string; className: string; Icon: typeof CheckCircle2 }
> = {
  pass: { label: "Met", className: "text-emerald-600 dark:text-emerald-400", Icon: CheckCircle2 },
  warning: {
    label: "Met, review required",
    className: "text-amber-600 dark:text-amber-400",
    Icon: AlertTriangle,
  },
  fail: { label: "Not met", className: "text-red-600 dark:text-red-400", Icon: XCircle },
  not_assessed: { label: "Not assessed", className: "text-muted-foreground", Icon: CircleDashed },
}

function stepTitle(check: ContractCheck): string {
  const spec = GOLDEN_PATH_STEPS.find((s) => s.key === check.matchedStep)
  if (spec) return spec.title
  return humanizeField(check.stepKey)
}

function reasons(check: ContractCheck): string[] {
  const out: string[] = []
  if (check.matchedStep == null) {
    out.push("No step in this arc matched the contract, so nothing was checked against it.")
    return out
  }
  for (const field of check.missingRequiredFields) {
    out.push(`Expected “${humanizeField(field)}” in the result, and it was not present.`)
  }
  for (const field of check.forbiddenFieldsPresent) {
    out.push(`“${humanizeField(field)}” must not appear in the result, and it did.`)
  }
  if (check.statusMismatch) {
    out.push("The step finished in a state the contract does not accept.")
  }
  return out
}

export function GoldenPathContractPanel({
  checks,
  hasRun,
}: {
  checks: ContractCheck[]
  hasRun: boolean
}) {
  const met = checks.filter((c) => c.status === "pass").length
  const failed = checks.filter((c) => c.status === "fail").length
  const assessed = checks.filter((c) => c.status !== "not_assessed").length

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Expected-output contracts</CardTitle>
        <CardDescription>
          Each contract this scenario defines, checked against what the arc&rsquo;s steps actually
          returned — not against a stored summary of them.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {checks.length === 0 ? (
          <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
            {hasRun
              ? "This scenario defines no expected-output contracts, so nothing was checked. A pass cannot be claimed without one."
              : "Run the arc to check it against this scenario’s contracts."}
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant="outline">
                {met} of {checks.length} met
              </Badge>
              {failed > 0 ? (
                <Badge variant="outline" className="border-red-500/50 text-red-600 dark:text-red-400">
                  {failed} not met
                </Badge>
              ) : null}
              {assessed < checks.length ? (
                <Badge variant="outline" className="text-muted-foreground">
                  {checks.length - assessed} not assessed
                </Badge>
              ) : null}
            </div>

            <ul className="space-y-2">
              {checks.map((check) => {
                const presentation = STATUS_PRESENTATION[check.status]
                const Icon = presentation.Icon
                const why = reasons(check)
                return (
                  <li key={check.contractId} className="rounded-md border p-3">
                    <div className="flex items-start gap-2">
                      <Icon
                        className={cn("mt-0.5 h-4 w-4 shrink-0", presentation.className)}
                        aria-hidden
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium">{stepTitle(check)}</span>
                          <span className={cn("text-xs", presentation.className)}>
                            {presentation.label}
                          </span>
                        </div>
                        {why.length > 0 ? (
                          <ul className="mt-1.5 space-y-1 text-xs text-muted-foreground">
                            {why.map((r) => (
                              <li key={r}>{r}</li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    </div>
                  </li>
                )
              })}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  )
}

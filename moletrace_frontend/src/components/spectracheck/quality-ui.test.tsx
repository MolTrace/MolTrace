import { cleanup, render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import { QualityAssessmentCard, MOCK_QUALITY_ASSESSMENT_PROPS } from "@/src/components/spectracheck/QualityAssessmentCard"
import { QualityFindingsTable, MOCK_QUALITY_FINDINGS } from "@/src/components/spectracheck/QualityFindingsTable"
import { QualityOverrideDialog } from "@/src/components/spectracheck/QualityOverrideDialog"
import { QualityStatusBadge } from "@/src/components/spectracheck/QualityStatusBadge"

function wrap(node: ReactNode) {
  return <TooltipProvider delayDuration={0}>{node}</TooltipProvider>
}

afterEach(() => {
  cleanup()
})

describe("QualityStatusBadge", () => {
  it("renders qc_pass", () => {
    render(<QualityStatusBadge status="qc_pass" />)
    expect(screen.getByText("QC pass")).toBeInTheDocument()
  })
})

describe("QualityFindingsTable", () => {
  it("renders mock findings", () => {
    render(<QualityFindingsTable findings={MOCK_QUALITY_FINDINGS} />)
    expect(screen.getByText("HASH_MISMATCH")).toBeInTheDocument()
    expect(screen.getByText("LAYER_SPARSE")).toBeInTheDocument()
  })
})

describe("QualityAssessmentCard", () => {
  it("renders mock props", () => {
    const onRun = vi.fn()
    render(wrap(<QualityAssessmentCard {...MOCK_QUALITY_ASSESSMENT_PROPS} onRunQc={onRun} />))
    expect(screen.getByText(/Quality control & evidence readiness/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Run QC/i })).toBeInTheDocument()
  })
})

describe("QualityOverrideDialog", () => {
  it("disables save without reason", () => {
    const onSave = vi.fn()
    render(
      <QualityOverrideDialog open onOpenChange={vi.fn()} onSave={onSave} />,
    )
    expect(screen.getByRole("button", { name: /Save override/i })).toBeDisabled()
  })
})

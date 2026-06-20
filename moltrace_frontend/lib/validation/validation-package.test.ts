import { describe, expect, it } from "vitest"
import { parseValidationPackage, qualStatusBadge } from "@/lib/validation/validation-package"

const RAW = {
  package_metadata: { release_id: 1, release_version: "13.0.0", package_schema_version: "1.0" },
  requirement_risk_test_traceability: { status: "no_traceability_generated", note: "No matrix generated." },
  iq_oq_pq_evidence: {
    iq: { status: "customer_supplied", note: "Installation Qualification is the customer's remit." },
    oq: { status: "pass", source: "ci_test_summary", passed: 142, failed: 0, skipped: 3, evidence: { coverage_percent: 87.4, total: 145 } },
    pq: { status: "customer_supplied", note: "Performance Qualification is the customer's remit." },
  },
  risk_summary: { high: 1, medium: 4, open: 2 },
  change_control_state: { validated: false, change_controlled: false, open_deviation_count: 0 },
  signatures: [],
  notice: "This validation package SUPPORTS a customer's GAMP 5 / CSA effort … it does not perform or replace the customer's CSV.",
}

describe("validation-package lib", () => {
  it("parses the package, mapping OQ counts + coverage from the evidence block", () => {
    const p = parseValidationPackage(RAW)!
    expect(p).not.toBeNull()
    expect(p.oq.status).toBe("pass")
    expect(p.oq.passed).toBe(142)
    expect(p.oq.failed).toBe(0)
    expect(p.oq.skipped).toBe(3)
    expect(p.oq.coveragePercent).toBe(87.4)
    expect(p.iq.status).toBe("customer_supplied")
    expect(p.pq.status).toBe("customer_supplied")
    expect(p.traceability.status).toBe("no_traceability_generated")
    expect(p.changeControl.validated).toBe(false)
    expect(p.changeControl.openDeviationCount).toBe(0)
    expect(p.riskSummary).toMatchObject({ high: 1, open: 2 })
    expect(p.notice).toMatch(/SUPPORTS/)
    expect(parseValidationPackage(null)).toBeNull()
  })

  it("maps IQ/PQ customer_supplied to a customer-responsibility badge, never pass", () => {
    expect(qualStatusBadge("customer_supplied")).toEqual({ tone: "customer", label: "Customer responsibility" })
    expect(qualStatusBadge("pass")).toEqual({ tone: "success", label: "Pass" })
    expect(qualStatusBadge("fail")).toEqual({ tone: "error", label: "Fail" })
    expect(qualStatusBadge("gaps_identified")).toMatchObject({ tone: "warning" })
    expect(qualStatusBadge("no_traceability_generated")).toMatchObject({ tone: "neutral" })
  })
})

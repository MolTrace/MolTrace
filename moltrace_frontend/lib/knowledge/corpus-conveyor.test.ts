// The corpus conveyor — the two rules the UI must not soften.
//
// Each test here guards a way the interface could let something through that
// the service would refuse, or present a governed step as an ordinary one.

import { beforeEach, describe, expect, it, vi } from "vitest"
import {
  DATASET_VERSION_SETTABLE_STATUSES,
  DATASET_VERSION_STATUSES,
} from "@/components/knowledge/knowledge-constants"
import {
  DEPLOYMENT_STATUS_PRESENTATION,
  GATE_ELIGIBILITY_NOTE,
  approvalProgress,
  approveDatasetVersion,
  conveyorSteps,
  metricLabel,
  readDeploymentStatus,
  readGateVerdict,
  type DatasetVersionApprovalState,
} from "@/lib/knowledge/corpus-conveyor"

const api = vi.hoisted(() => ({ apiFetch: vi.fn() }))
vi.mock("@/lib/api/client", () => ({ apiFetch: (...a: unknown[]) => api.apiFetch(...a) }))

beforeEach(() => {
  api.apiFetch.mockReset()
  api.apiFetch.mockResolvedValue({})
})

function state(partial: Partial<DatasetVersionApprovalState>): DatasetVersionApprovalState {
  return {
    dataset_version_id: 1,
    status: "draft",
    approvals: [],
    distinct_approvers: 0,
    approvals_required: 2,
    promoted: false,
    human_review_required: true,
    ...partial,
  }
}

describe("approving carries no approver identity", () => {
  it("sends the comment and nothing else", async () => {
    await approveDatasetVersion(4, "Checked the splits.")
    const [, init] = api.apiFetch.mock.calls[0] as [string, { body: Record<string, unknown> }]
    expect(Object.keys(init.body)).toEqual(["comment"])
  })

  it("sends an empty body rather than a blank comment", async () => {
    await approveDatasetVersion(4, "   ")
    const [, init] = api.apiFetch.mock.calls[0] as [string, { body: Record<string, unknown> }]
    expect(init.body).toEqual({})
  })

  it("never puts an approver, reviewer or user field on the wire", async () => {
    // A caller-supplied approver would let one person nominate another as the
    // second, which is the entire control being bought.
    await approveDatasetVersion(4, "ok")
    const [, init] = api.apiFetch.mock.calls[0] as [string, { body: Record<string, unknown> }]
    for (const key of Object.keys(init.body)) {
      expect(key).not.toMatch(/approver|reviewer|user|email|principal/i)
    }
  })
})

describe("approval progress is a count, not a tick", () => {
  it("distinguishes awaiting-a-second from not-approved", () => {
    const none = approvalProgress(state({ distinct_approvers: 0 }))
    const one = approvalProgress(state({ distinct_approvers: 1 }))
    expect(none.statusLabel).not.toBe(one.statusLabel)
    expect(one.statusLabel).toMatch(/second approver/i)
    expect(one.countLabel).toBe("1 of 2 approvals")
  })

  it("says the second approver has to be someone else", () => {
    expect(approvalProgress(state({ distinct_approvers: 1 })).statusLabel).toMatch(/someone other/i)
  })

  it("uses the server's required count rather than a hardcoded 2", () => {
    // Hardcoding it would leave the screen showing "of 2" after the rule changed.
    const progress = approvalProgress(state({ distinct_approvers: 1, approvals_required: 3 }))
    expect(progress.countLabel).toBe("1 of 3 approvals")
    expect(progress.statusLabel).toMatch(/2 more approvers/i)
  })

  it("reads a missing state as no approvals, never as approved", () => {
    const progress = approvalProgress(null)
    expect(progress.promoted).toBe(false)
    expect(progress.distinct).toBe(0)
  })
})

describe("conveyor steps mirror what the service will accept", () => {
  it("refuses a rollout without a passed check", () => {
    expect(conveyorSteps("draft").canCanary).toBe(false)
    expect(conveyorSteps("gate_failed").canCanary).toBe(false)
    expect(conveyorSteps("gate_passed").canCanary).toBe(true)
  })

  it("refuses promotion straight off a passed check — a rollout has to run first", () => {
    expect(conveyorSteps("gate_passed").canPromote).toBe(false)
    expect(conveyorSteps("canary").canPromote).toBe(true)
  })

  it("does not offer a re-check on something already rolling out or in service", () => {
    // Re-judging it would rewind its status while its rollout timestamps still
    // said it shipped — a record that contradicts itself.
    expect(conveyorSteps("canary").canGate).toBe(false)
    expect(conveyorSteps("promoted").canGate).toBe(false)
    expect(conveyorSteps("gate_failed").canGate).toBe(true)
  })

  it("offers nothing further once a candidate is in service", () => {
    expect(conveyorSteps("promoted")).toEqual({ canGate: false, canCanary: false, canPromote: false })
  })

  it("reads an unrecognised status as the earliest step, not the latest", () => {
    expect(readDeploymentStatus("something_new")).toBe("draft")
    expect(readDeploymentStatus(null)).toBe("draft")
  })
})

describe("a passed check is eligibility, not approval", () => {
  it("does not label a cleared check as approved or promoted", () => {
    const label = DEPLOYMENT_STATUS_PRESENTATION.gate_passed.label
    expect(label).not.toMatch(/approved|promoted|deployed|live|shipped/i)
    expect(DEPLOYMENT_STATUS_PRESENTATION.gate_passed.description).toMatch(/not an approval/i)
  })

  it("keeps human sign-off true when the field is absent", () => {
    // A missing field must not read as "no sign-off needed".
    expect(readGateVerdict({}).requiresHumanSignoff).toBe(true)
    expect(readGateVerdict({ promotable: true }).requiresHumanSignoff).toBe(true)
    expect(readGateVerdict({ requires_human_signoff: false }).requiresHumanSignoff).toBe(false)
  })

  it("states that clearing the check deploys nothing", () => {
    expect(GATE_ELIGIBILITY_NOTE).toMatch(/not sign-off/i)
  })
})

describe("the gate verdict is read out, not summarised", () => {
  it("keeps every reason verbatim and in order", () => {
    const reasons = [
      "Safety-flag recall is missing or out of range [0, 1]; failing closed.",
      "Challenger does not dominate the champion's metric vector; blocked.",
    ]
    expect(readGateVerdict({ reasons }).reasons).toEqual(reasons)
  })

  it("treats an unchecked candidate as having no verdict rather than a failed one", () => {
    const verdict = readGateVerdict({})
    expect(verdict.present).toBe(false)
    expect(verdict.promotable).toBe(false)
  })

  it("does not read a non-boolean as a pass", () => {
    expect(readGateVerdict({ promotable: "true" }).promotable).toBe(false)
    expect(readGateVerdict({ promotable: 1 }).promotable).toBe(false)
  })

  it("carries the blocking measure's name, which differs by model", () => {
    expect(readGateVerdict({ blocking_metric_name: "citation_support_recall" }).blockingMetricName).toBe(
      "citation_support_recall",
    )
    expect(readGateVerdict({ blocking_metric_name: "  " }).blockingMetricName).toBeNull()
  })

  it("humanizes a measure name for display without renaming the key", () => {
    expect(metricLabel("citation_support_recall")).toBe("Citation support recall")
  })
})

describe("a dataset version cannot be promoted by setting its status", () => {
  it("leaves `approved` out of the statuses a person can set", () => {
    // The service refuses a status set straight to approved, on creation as well
    // as on edit. Offering it would be a dropdown option that always fails.
    expect(DATASET_VERSION_SETTABLE_STATUSES).not.toContain("approved")
  })

  it("keeps every other status settable, so this is a removal and not a rewrite", () => {
    expect(DATASET_VERSION_SETTABLE_STATUSES).toEqual(
      DATASET_VERSION_STATUSES.filter((s) => s !== "approved"),
    )
  })

  it("still recognises `approved` as a status a version can be in", () => {
    // Filtering by it, and displaying it, both read rather than set.
    expect(DATASET_VERSION_STATUSES).toContain("approved")
  })
})

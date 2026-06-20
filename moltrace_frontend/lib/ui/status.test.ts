import { describe, expect, it } from "vitest"
import { humanizeField, statusLabel, statusTone } from "@/lib/ui/status"

describe("status helpers", () => {
  it("classifies known + fuzzy status tokens into tones", () => {
    expect(statusTone("approved")).toBe("success")
    expect(statusTone("rejected")).toBe("danger")
    expect(statusTone("ready_for_qa_review")).toBe("warning")
    expect(statusTone("in_progress")).toBe("info")
    expect(statusTone("archived")).toBe("neutral")
    // fuzzy fallback for unknown tokens
    expect(statusTone("submission_failed")).toBe("danger")
    expect(statusTone("auto_approved")).toBe("success")
    expect(statusTone("")).toBe("neutral")
  })

  it("humanizes status enums (keeping acronyms)", () => {
    expect(statusLabel("ready_for_qa_review")).toBe("Ready for QA review")
    expect(statusLabel("in_progress")).toBe("In progress")
    expect(statusLabel("customer_supplied")).toBe("Customer supplied")
    expect(statusLabel("")).toBe("—")
  })

  it("humanizes snake_case field names, stripping _id/_json + casing acronyms", () => {
    expect(humanizeField("bo_run_id")).toBe("BO run")
    expect(humanizeField("result_type")).toBe("Result type")
    expect(humanizeField("recommendation_batch_id")).toBe("Recommendation batch")
    expect(humanizeField("linked_spectracheck_session_id")).toBe("Linked SpectraCheck session")
    expect(humanizeField("metadata_json")).toBe("Metadata")
  })
})

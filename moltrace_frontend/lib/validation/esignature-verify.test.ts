import { describe, expect, it } from "vitest"
import {
  parseManifestation,
  parseVerification,
  verifyStatus,
  type ESignatureVerification,
} from "@/lib/validation/esignature-verify"

const v = (over: Partial<ESignatureVerification>): ESignatureVerification => ({
  signatureId: 1,
  bound: true,
  valid: null,
  hashMatches: null,
  contentMatches: null,
  recordContentHash: null,
  recomputedContentHash: null,
  reason: "",
  ...over,
})

describe("esignature-verify lib", () => {
  it("parses a verification response defensively", () => {
    const parsed = parseVerification({
      signature_id: 5,
      bound: false,
      valid: null,
      hash_matches: null,
      content_matches: null,
      record_content_hash: null,
      recomputed_content_hash: null,
      reason: "legacy_unbound_signature",
    })!
    expect(parsed.signatureId).toBe(5)
    expect(parsed.bound).toBe(false)
    expect(parsed.valid).toBeNull()
    expect(parsed.reason).toBe("legacy_unbound_signature")
    expect(parseVerification(null)).toBeNull()
  })

  it("parses a manifestation incl. the compliance notice", () => {
    const m = parseManifestation({
      printed_name: "Dr. A",
      signer_email: "a@x.com",
      signature_meaning: "approved",
      meaning_label: "Approved by",
      signed_at_utc: "2026-06-16T00:00:00+00:00",
      reason: "release",
      target_type: "reaction_project",
      target_id: 2,
      record_content_hash: "sha256:abc",
      signature_digest: "sha256:def",
      binding_status: "bound",
      authentication_method: "password+webauthn",
      step_up_factor: "webauthn",
      step_up_aal: "AAL2",
      attestation_text: "Approved by Dr. A …",
      compliance_notice: "Supports 21 CFR Part 11; not a compliance determination for your use.",
    })!
    expect(m.meaningLabel).toBe("Approved by")
    expect(m.bindingStatus).toBe("bound")
    expect(m.stepUpAal).toBe("AAL2")
    expect(m.complianceNotice).toMatch(/Supports 21 CFR Part 11/)
  })

  it("maps every verify state to a UI status", () => {
    expect(verifyStatus(v({ bound: false, reason: "legacy_unbound_signature" }))).toMatchObject({
      tone: "neutral",
      label: "Unbound (legacy)",
    })
    expect(verifyStatus(v({ bound: true, valid: true }))).toMatchObject({ tone: "success", label: "Verified" })
    const digest = verifyStatus(v({ bound: true, valid: false, reason: "digest_mismatch" }))
    expect(digest.tone).toBe("error")
    expect(digest.detail).toMatch(/tampered/i)
    const changed = verifyStatus(v({ bound: true, valid: false, reason: "record_content_changed" }))
    expect(changed.tone).toBe("error")
    expect(changed.detail).toMatch(/edited after signing/i)
    expect(verifyStatus(v({ bound: true, valid: null, reason: "unknown" })).tone).toBe("indeterminate")
  })
})

import userEvent from "@testing-library/user-event"
import { render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { TraceableFigure } from "@/components/trust/traceable-figure"
import { chainFindings, chainOutcome, describeBreak } from "@/components/trust/chain-verification"
import type { SubjectAuditChainVerification } from "@/components/trust/chain-verification"

const apiFetchMock = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api/client", () => ({ apiFetch: apiFetchMock }))

afterEach(() => {
  apiFetchMock.mockReset()
})

function verification(over: Partial<SubjectAuditChainVerification> = {}): SubjectAuditChainVerification {
  return {
    subject_type: "regulatory_dossier",
    subject_id: 7,
    entry_count: 3,
    verified_count: 3,
    ok: true,
    content_ok: true,
    chain_ok: true,
    first_break_seq: null,
    break_kind: null,
    chain_break_kind: null,
    key_id: "k1",
    detail: "ok",
    ...over,
  }
}

describe("chain verification rules", () => {
  it("treats an empty chain as unchecked, never as a pass", () => {
    // The single most misleading pixel this feature could ship: `entry_count: 0`
    // rendering as verified. Nothing was checked, so nothing is established.
    const empty = verification({ entry_count: 0, verified_count: 0, ok: false, detail: "no_chained_entries" })
    expect(chainOutcome(empty)).toBe("unchecked")

    // And it must not be reachable as a pass even if `ok` were somehow true.
    expect(chainOutcome(verification({ entry_count: 0, ok: true }))).toBe("unchecked")
  })

  it("separates 'nothing altered' from 'nothing removed'", () => {
    // The subject's own slice can establish the first but never the second, so
    // collapsing them into one indicator would overstate what was checked.
    const findings = chainFindings(verification({ content_ok: true, chain_ok: false }))
    expect(findings).toHaveLength(2)
    expect(findings[0]?.ok).toBe(true)
    expect(findings[1]?.ok).toBe(false)
  })

  it("names the cause from break_kind, never from detail", () => {
    const altered = verification({ ok: false, content_ok: false, break_kind: "entry_hash_mismatch" })
    expect(describeBreak(altered)).toMatch(/altered/i)

    expect(describeBreak(verification({ ok: false, chain_break_kind: "sequence_gap" }))).toMatch(/removed/i)
    expect(describeBreak(verification({ ok: false, chain_break_kind: "prev_hash_mismatch" }))).toMatch(/order/i)

    // An unknown kind yields no invented explanation, even with prose in `detail`.
    expect(describeBreak(verification({ ok: false, break_kind: "brand_new_kind", detail: "chain exploded" }))).toBeNull()
  })
})

describe("TraceableFigure", () => {
  it("renders a visible 'not traced' marker instead of a bare number", () => {
    render(<TraceableFigure value={0.12} unit="%" />)
    expect(screen.getByText(/not traced/i)).toBeInTheDocument()
  })

  it("keeps the rule set version with the figure and human review visible", () => {
    render(<TraceableFigure value={0.12} unit="%" ruleSetVersion="ich-q3b-2026.1" reviewRequired />)
    expect(screen.getByText("ich-q3b-2026.1")).toBeInTheDocument()
    expect(screen.getByText(/human review required/i)).toBeInTheDocument()
  })

  it("reports an empty chain as 'nothing was checked' and not as a pass", async () => {
    apiFetchMock.mockResolvedValueOnce(
      verification({ entry_count: 0, verified_count: 0, ok: false, detail: "no_chained_entries" }),
    )
    render(<TraceableFigure value={1} subject={{ type: "regulatory_dossier", id: 7 }} />)
    await userEvent.click(screen.getByRole("button", { name: /verify the trail/i }))

    await waitFor(() => expect(screen.getByText(/nothing was checked/i)).toBeInTheDocument())
    expect(screen.getByText(/this is not a pass/i)).toBeInTheDocument()
    expect(screen.queryByText(/trail verified/i)).not.toBeInTheDocument()
  })

  it("shows a named cause when the chain is broken", async () => {
    apiFetchMock.mockResolvedValueOnce(
      verification({ ok: false, content_ok: false, break_kind: "entry_hash_mismatch", first_break_seq: 4 }),
    )
    render(<TraceableFigure value={1} subject={{ type: "regulatory_dossier", id: 7 }} />)
    await userEvent.click(screen.getByRole("button", { name: /verify the trail/i }))

    await waitFor(() => expect(screen.getByText(/trail could not be verified/i)).toBeInTheDocument())
    expect(screen.getByText(/altered after it was written/i)).toBeInTheDocument()
  })

  it("does not report a verification failure as a finding about the record", async () => {
    apiFetchMock.mockRejectedValueOnce(new Error("network"))
    render(<TraceableFigure value={1} subject={{ type: "regulatory_dossier", id: 7 }} />)
    await userEvent.click(screen.getByRole("button", { name: /verify the trail/i }))

    await waitFor(() =>
      expect(screen.getByText(/not a finding about the record/i)).toBeInTheDocument(),
    )
  })

  it("says a source is unavailable rather than fabricating a link", async () => {
    apiFetchMock.mockRejectedValueOnce(new Error("404"))
    render(
      <TraceableFigure
        value={0.12}
        citation={{
          id: 1,
          source_id: 99,
          citation_label: "ICH Q3B(R2) §4.1",
          created_at: "2026-01-01T00:00:00Z",
        }}
      />,
    )
    await userEvent.click(screen.getByRole("button", { name: /traced to source/i }))

    await waitFor(() => expect(screen.getByText(/could not be resolved/i)).toBeInTheDocument())
    // Nothing clickable is offered for an unresolvable source.
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
  })
})

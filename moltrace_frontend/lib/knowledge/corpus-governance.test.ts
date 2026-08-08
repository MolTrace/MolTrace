// Corpus governance — the distinctions that must not collapse.
//
// Each test here guards a state the UI could merge into a neighbouring one and
// thereby assert something the corpus does not actually know.

import { describe, expect, it, vi, beforeEach } from "vitest"
import {
  LOCATOR_ADDRESS_MISSING,
  LOCATOR_MISSING_LABEL,
  PROVENANCE_PRESENTATION,
  REVIEW_STATE_PRESENTATION,
  SOURCE_SUPERSEDED_REASON,
  changedFieldLabel,
  changedFieldsSentence,
  fetchCurrentRevisionIds,
  hasReviewState,
  locatorAddress,
  provenanceState,
  readLocators,
  readReviewState,
  readSupersededTask,
} from "@/lib/knowledge/corpus-governance"

const api = vi.hoisted(() => ({ apiFetch: vi.fn() }))
vi.mock("@/lib/api/client", () => ({ apiFetch: (...a: unknown[]) => api.apiFetch(...a) }))

beforeEach(() => {
  api.apiFetch.mockReset()
})

describe("review state: unreviewed is not approved", () => {
  it("reads null as unreviewed, never as accepted", () => {
    expect(readReviewState(null)).toBe("unreviewed")
    expect(readReviewState(undefined)).toBe("unreviewed")
  })

  it("reads the backend's literal 'unreviewed' the same way as null", () => {
    // search_knowledge treats a NULL review_status and the string "unreviewed"
    // as the same state, so the UI must too.
    expect(readReviewState("unreviewed")).toBe("unreviewed")
  })

  it("does not treat an unrecognised value as approval", () => {
    // An unknown string is not evidence that someone signed off.
    expect(readReviewState("looks_fine")).toBe("unreviewed")
    expect(readReviewState(42)).toBe("unreviewed")
  })

  it("recognises the two real decisions, case-insensitively", () => {
    expect(readReviewState("accepted")).toBe("accepted")
    expect(readReviewState("  Rejected ")).toBe("rejected")
  })

  it("labels unreviewed plainly, without inventing a confident third state", () => {
    const label = REVIEW_STATE_PRESENTATION.unreviewed.label
    expect(label).toBe("Not yet reviewed")
    // "Pending"/"Provisional"/"Approved" all imply something that has not happened.
    expect(label).not.toMatch(/pending|provisional|approved|validated|verified/i)
    // And it must not read as a bare absence either.
    expect(label).not.toBe("—")
  })

  it("gives rejected its own tone so it cannot be merely sorted lower", () => {
    expect(REVIEW_STATE_PRESENTATION.rejected.tone).toBe("rejected")
    expect(REVIEW_STATE_PRESENTATION.accepted.tone).not.toBe(
      REVIEW_STATE_PRESENTATION.rejected.tone,
    )
  })
})

describe("citations have no review state at all", () => {
  it("reports citations as carrying no review state", () => {
    // ExtractedCitation has no review_status field, which is also why search
    // cannot filter citations. Rendering "Not yet reviewed" on one would invent
    // a review process that does not exist for it.
    expect(hasReviewState("citation")).toBe(false)
  })

  it("reports the record types that do carry one", () => {
    for (const t of ["analytical", "reaction", "regulatory"]) {
      expect(hasReviewState(t)).toBe(true)
    }
  })
})

describe("provenance: stale and unknown are different answers", () => {
  it("marks a record whose source moved on", () => {
    expect(provenanceState(3, 5)).toBe("superseded")
  })

  it("marks a record extracted from the current version", () => {
    expect(provenanceState(5, 5)).toBe("current")
  })

  it("treats a null source_revision_id as unknown, never as current", () => {
    // The backend deliberately did not backfill this. Claiming those records
    // came from what the source says now would assert something unknowable —
    // and would be most likely false exactly where in-place editing happened.
    expect(provenanceState(null, 5)).toBe("unknown")
    expect(provenanceState(undefined, 5)).toBe("unknown")
    expect(provenanceState(null, 5)).not.toBe("current")
  })

  it("treats an unresolved source as unknown, not as unchanged", () => {
    // We cannot conclude "unchanged" from a comparison we could not make.
    expect(provenanceState(3, null)).toBe("unknown")
  })

  it("describes unknown as not-known-current rather than as fine", () => {
    const description = PROVENANCE_PRESENTATION.unknown.description
    expect(PROVENANCE_PRESENTATION.unknown.label).toBe("Source version not recorded")
    expect(description).toMatch(/not known to be up to date/i)
  })
})

describe("batching the source lookup", () => {
  it("fetches each distinct source once, not once per row", async () => {
    api.apiFetch.mockImplementation(async (path: string) => {
      const id = Number(path.split("/").pop())
      return { id, current_revision_id: id * 10 }
    })
    // Ten rows drawn from three sources must cost three requests.
    const map = await fetchCurrentRevisionIds([1, 1, 2, 2, 2, 3, 1, 3, 2, 1])
    expect(api.apiFetch).toHaveBeenCalledTimes(3)
    expect(map.get(1)).toBe(10)
    expect(map.get(3)).toBe(30)
  })

  it("omits a source that fails to load, so it reads as unknown", async () => {
    api.apiFetch.mockRejectedValue(new Error("nope"))
    const map = await fetchCurrentRevisionIds([7])
    expect(map.has(7)).toBe(false)
    // An absent entry feeds null into provenanceState → unknown, not current.
    expect(provenanceState(4, map.get(7) ?? null)).toBe("unknown")
  })
})

describe("changed_fields are humanized for display only", () => {
  it("humanizes the wire keys a reader would otherwise see raw", () => {
    expect(changedFieldLabel("reliability_label")).toBe("reliability label")
    expect(changedFieldLabel("doi")).toBe("DOI")
    expect(changedFieldLabel("publication_date")).toBe("publication date")
  })

  it("builds a sentence fragment from several fields", () => {
    expect(changedFieldsSentence(["reliability_label"])).toBe("reliability label")
    expect(changedFieldsSentence(["reliability_label", "doi"])).toBe("reliability label and DOI")
    expect(changedFieldsSentence([])).toBe("")
    expect(changedFieldsSentence(null)).toBe("")
  })
})

describe("source_superseded review tasks", () => {
  it("reads the context off a superseded task", () => {
    const ctx = readSupersededTask({
      reason: SOURCE_SUPERSEDED_REASON,
      changed_fields: ["reliability_label"],
      extracted_from_revision: 1,
      current_revision: 2,
    })
    expect(ctx).not.toBeNull()
    expect(ctx?.changedFields).toEqual(["reliability_label"])
    expect(ctx?.extractedFromRevision).toBe(1)
    expect(ctx?.currentRevision).toBe(2)
  })

  it("returns null for a task raised for any other reason", () => {
    expect(readSupersededTask({ reason: "manual_review" })).toBeNull()
    expect(readSupersededTask({})).toBeNull()
    expect(readSupersededTask(null)).toBeNull()
  })
})

describe("locators: not-recorded is not not-there", () => {
  const locator = {
    citation_id: 7,
    citation_label: "Smith 2024, SI",
    source_id: 3,
    source_revision_id: 2,
    source_file_id: null,
    page_number: 12,
    section_title: "Methods",
    paragraph_number: 3,
    quote_excerpt: "The reaction was run at 40 °C for 6 h.",
  }

  it("reads a well-formed locator through unchanged", () => {
    expect(readLocators([locator])).toEqual([locator])
  })

  it("drops an entry with no citation or source to point at, rather than inventing one", () => {
    expect(readLocators([{ ...locator, citation_id: null }])).toEqual([])
    expect(readLocators([{ ...locator, source_id: "3" }])).toEqual([])
    expect(readLocators([null, "nope", 42])).toEqual([])
  })

  it("reads a missing array as no locators, not as an error", () => {
    expect(readLocators(undefined)).toEqual([])
    expect(readLocators(null)).toEqual([])
    expect(readLocators({})).toEqual([])
  })

  it("normalises a blank quote or section to null instead of an empty string", () => {
    const [read] = readLocators([{ ...locator, quote_excerpt: "   ", section_title: "" }])
    expect(read.quote_excerpt).toBeNull()
    expect(read.section_title).toBeNull()
  })

  it("builds the address from whichever parts were recorded", () => {
    expect(locatorAddress(locator)).toBe("Page 12 · Methods · Paragraph 3")
    expect(locatorAddress({ ...locator, section_title: null })).toBe("Page 12 · Paragraph 3")
    expect(locatorAddress({ ...locator, page_number: null, paragraph_number: null })).toBe("Methods")
  })

  it("returns an empty address rather than guessing a page", () => {
    const bare = { ...locator, page_number: null, section_title: null, paragraph_number: null }
    expect(locatorAddress(bare)).toBe("")
    // Callers render LOCATOR_ADDRESS_MISSING here. The one thing that must never
    // happen is a default page number standing in for one nobody wrote down.
    expect(LOCATOR_ADDRESS_MISSING).toMatch(/not recorded/i)
  })

  it("says the passage was not recorded, without claiming there is no passage", () => {
    expect(LOCATOR_MISSING_LABEL).toMatch(/not recorded/i)
    // "No source", "unsourced" and the like would assert something stronger than
    // "nobody wrote down where in the source this came from".
    expect(LOCATOR_MISSING_LABEL).not.toMatch(/no source|unsourced|none/i)
  })
})

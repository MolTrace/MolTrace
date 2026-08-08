# FE Handoff — Knowledge corpus governance: rejected facts, and sources that change

Two backend changes shipped together. Both are about the same thing: a curated corpus has
to be able to show *what a fact was justified by, and whether anyone still stands behind it*.
Neither is a redesign — both add fields to models the frontend already renders.

**Nothing is blocked on further backend work.** Steps 1–2 are mechanical; 3–6 are the UI.

---

## 1. Where to work, and regenerate the contract first

```bash
cd moltrace_frontend
pnpm generate:openapi
```

The backend must be running on `:8000` for that to work:

```bash
cd moltrace_backend && uv run python -m uvicorn nmrcheck.main:app --host 127.0.0.1 --port 8000
```

`pnpm generate:openapi` rewrites `src/lib/api/schema.d.ts`. Do this **before** touching any
component — the types below do not exist in the checked-in schema yet.

Remember `app/` at the project root is the routed tree. `src/app/` is the non-routed mirror
and does not render.

## 2. What changed in the contract, by name

**New route**

| Method | Path | Returns |
|---|---|---|
| `GET` | `/knowledge/sources/{source_id}/revisions` | `KnowledgeSourceRevision[]`, newest first; `404` if the source does not exist |

**New query parameter**

| Route | Param | Default |
|---|---|---|
| `GET /knowledge/search` | `include_rejected: boolean` | `false` |

**New fields on models you already render**

| Model | Field | Type |
|---|---|---|
| `KnowledgeSource` | `current_revision_id` | `number \| null` |
| `KnowledgeSourceUpdate` | `change_reason` | `string \| null` (max 500) |
| `ExtractedReactionRecord` | `source_revision_id` | `number \| null` |
| `ExtractedAnalyticalRecord` | `source_revision_id` | `number \| null` |
| `ExtractedRegulatoryRecord` | `source_revision_id` | `number \| null` |
| `ExtractedCitation` | `source_revision_id` | `number \| null` |

**New model** — `KnowledgeSourceRevision`:

```ts
{
  id: number
  source_id: number
  revision_number: number
  supersedes_revision_id: number | null
  title: string
  source_type: string
  source_url: string | null
  doi: string | null
  patent_number: string | null
  jurisdiction_id: number | null
  publisher: string | null
  publication_date: string | null   // ISO 8601
  status: string
  reliability_label: string
  changed_fields: string[]          // wire keys, e.g. ["reliability_label"] — humanize for display
  change_reason: string | null
  created_by: string | null
  created_at: string                // ISO 8601
  is_current: boolean
  human_review_required: boolean    // always true
}
```

`KnowledgeSourceUpdate` is `extra="forbid"`. Sending any key not on that model returns a
100% `422`. If you get one, A/B-post the same body to a nonexistent source id: `422` means
the shape is wrong, `404` means the shape was fine.

## 3. Search no longer returns rejected facts

Previously `search_knowledge` filtered on text match alone, so a record a reviewer had
explicitly **rejected** came back beside an accepted one, indistinguishable. Results now
default to accepted-or-unreviewed.

What the UI needs to do:

1. **Show the state on every hit.** Every record already carries `review_status`
   (`"accepted"`, `"rejected"`, or `null`). `null` means nobody has looked at it yet — that
   is a genuinely different thing from "approved" and must never be presented as the same.
   Suggested display: an "Accepted" marker, and "Not yet reviewed" for `null`. Do not invent
   a third confident-sounding label for `null`.
2. **Offer `include_rejected` as an explicit, off-by-default control.** Label it for what it
   does — something like "Include material a reviewer refused" — not "Show all".
3. **When `include_rejected` is on, rejected hits must be visually distinct**, not merely
   sorted lower. The whole reason the flag exists is that a rejected fact looks exactly like
   an accepted one otherwise.

Note the gap, and do not paper over it: **citations are not filtered**, because they have no
`review_status` field at all. Do not render a review state for a citation — there is nothing
behind it.

## 4. Sources are superseded, never edited

Editing a source used to overwrite the row. `publication_date`, `doi` and
`reliability_label` are exactly the fields a downstream extraction was justified by, so an
in-place edit left records citing a source that now said something else.

Now every change appends a revision and the predecessor stays readable forever. The
**source id is unchanged in meaning** — it is still the living source — so every existing
link, route and stored `source_id` keeps working. Nothing you already built breaks.

What the UI needs:

1. **A history view** on the source detail surface, from
   `GET /knowledge/sources/{id}/revisions`. Newest first; mark the one with
   `is_current: true`. Each entry shows `changed_fields` (humanized — `reliability_label` →
   "reliability label"), `change_reason`, `created_by` and `created_at`.
2. **A reason field on the edit form**, posting `change_reason` in the `PATCH` body. It is
   optional on the wire; treat it as expected-but-not-enforced in the UI. Do not block the
   edit on it.
3. **A "source has changed since this was extracted" marker** on any record whose
   `source_revision_id` is not the source's `current_revision_id`. This is the whole payoff —
   it is what makes a stale justification visible at all.

   Be aware of the shape here: records carry `source_revision_id`, but `current_revision_id`
   lives on the source, so comparing them needs the source too. On a detail view that is one
   extra fetch and fine. On a list or search results page it is an N+1 — fetch the distinct
   `source_id`s once and compare in memory rather than per row. If that turns out to be
   awkward in practice, say so and the comparison can be moved onto the record server-side;
   it was left off deliberately rather than guessed at.
4. **`source_revision_id: null` means "extracted before revisions existed"** — unknown
   provenance, not current. Render it as unknown ("Source version not recorded"), never as
   up to date. The backend deliberately did not backfill this: claiming those records came
   from what the source says now would be asserting something unknowable, and most likely
   false exactly where in-place editing already happened.

## 5. Superseding raises review tasks — it does not overturn decisions

When a source is superseded, every derived record gets an **open review task** in the
existing `/knowledge/review-tasks` queue, titled with what moved (e.g. "Re-check this
record: its source changed (reliability label)."). Its `metadata_json` carries
`reason: "source_superseded"`, `changed_fields`, `extracted_from_revision` and
`current_revision`.

Records **keep their own review decision** and stay bound to their own revision. So a record
can legitimately read "Accepted" *and* carry an open re-check task at the same time — that
combination is correct, not a bug, and the UI should be able to show both without implying
the acceptance was withdrawn. A human decides whether the change matters.

These tasks land in the review queue you already render. No new surface is required for
them; they mainly need the title and the `source_superseded` reason to be legible.

## 6. Verify

```bash
cd moltrace_frontend
pnpm typecheck && pnpm lint && pnpm test -- --run
```

`pnpm build` does **not** typecheck (`next.config.mjs` sets `typescript.ignoreBuildErrors`),
so `pnpm typecheck` is the real gate.

Manual checks worth doing, in this order:

1. Create a source, upload text, run an extraction — the record comes back with a
   `source_revision_id` matching the source's `current_revision_id`.
2. `PATCH` the source's `reliability_label` with a `change_reason`.
3. The revisions route now returns two entries; revision 1 still shows the **old** label.
   That is the guarantee — if revision 1 shows the new value, something is wrong.
4. The record's `source_revision_id` is unchanged and now differs from
   `current_revision_id` → your "source has changed" marker should appear.
5. An open review task exists for that record, and the record still reads its prior
   review state.

## 7. Copy constraints

Per the repo convention, nothing user-visible may contain endpoint paths, HTTP verbs, status
codes, `_json` field names, or the word "backend". `changed_fields` arrives as wire keys —
humanize for display only, and never rename the keys you send back.

`human_review_required` is `true` on every revision. Existing surfaces already handle this
flag; keep the same treatment rather than adding a second, differently-worded caveat.

# FE handoff — a FID reviewer can now find the run they are asked to sign off

**Backend commit:** this change (follows `653b402`, which opened the write side only)
**Contract:** **yes.** `schema.d.ts` is regenerated and committed — re-run
`pnpm generate:openapi` only if you pull the backend separately.
**Pages affected:** `components/spectracheck/spectracheck-fid-run-review.tsx`,
`lib/fid/fid-run-review.ts`, and the SpectraCheck Raw FID tab.

---

## 1. What changed

`653b402` let a colleague — not only a platform admin — approve a FID run. It opened
`POST /fid/runs/{id}/review|approve|reject|request-changes` and stopped there. Discovery
stayed owner-scoped, so a non-admin peer could record a verdict on a run they could not
list, open, or read the history of. The header comments in both files above documented
this; they have been updated.

Read access is now defined to be co-extensive with the review duty. `GET /fid/runs`
returns a run when:

1. **you produced it** — unchanged, nobody loses their own work; or
2. **it is an open item on your team's queue** — the author shares an active organization
   with you *and* `review_status` is `pending_review` or `needs_revision`; or
3. **you already recorded a decision on it** — whatever its status is now.

Clause 2 lapses on completion: a colleague's `approved` or `rejected` run stops being
listed. Clause 3 is what keeps a reviewer able to open what they signed.

**The write routes now enforce the same predicate.** A run you cannot read returns the
same non-leaking `404` on `POST`. This narrows `653b402`, which left the POST ungated.

## 2. The status codes you will see

| Case | Before | Now |
|---|---|---|
| Peer reads a teammate's run awaiting review | `404` | **`200`** |
| Peer reads a teammate's *finished* run | `404` | `404` (unchanged) |
| Reviewer of record re-opens the run they signed | `404` | **`200`** |
| Peer in a different org reads or **writes** | `404` read / **`200` write** | `404` both |
| Author posts a review of their own run | `409` | `409` (unchanged) |
| Admin / system key | `200` | `200` (unchanged) |

The author's refusal stays **409**, not 404 — they can see the run, they just may not be
the one to approve it. Keep `selfReviewMessage` for that path.

## 3. Contract delta, by name

**`FIDRunRecord`** gains two per-request fields (never stored):

- `viewer_is_author: boolean` — you created this run. `true` for an admin who is also the
  author.
- `viewer_can_review: boolean` — you may record a decision. `false` for the author, except
  for an admin / system key.

The list is now **mixed**, so use these rather than comparing `user_id` to the signed-in
user. `viewer_can_review === false` is the pre-flight for the 409 — disable the verdict
buttons instead of letting the POST fail and explaining afterwards.

**`GET /fid/runs`** gains `scope?: "all" | "mine" | "review_queue"` (default `"all"`).
`review_queue` returns open runs awaiting somebody else's verdict, excluding your own.
It narrows within what you can already see; it grants nothing. `fetchFidRuns(limit)` in
`lib/fid/fid-run-review.ts` does **not** pass it yet — add the parameter when you build
the queue view.

**`NMRRawFIDProcessResponse`** gains `fid_run_id?: number | null`. `POST
/nmr/raw-fid/process` always persisted a run but never reported which, and the model is
`extra="forbid"` — that omission is why the Raw FID tab drives review off the run *list*.
The panel can now anchor to the run just processed. Note this only helps the run **you**
created; reviewing a colleague's work starts from the list by definition.

## 4. The empty state is a real state

A user who belongs to **no organization** has no colleagues, so their review queue is
correctly empty and always will be. Organizations are created explicitly (`POST
/organizations`, SCIM, or SSO JIT provisioning) — signing up does not create one. Say
this in the empty state rather than rendering a bare "no runs" that reads as a fault:
something like *"No runs are waiting on you. Peer review draws on your organization's
members — ask an administrator to add you to one if you expect to see colleagues' runs."*
The same is true for a run whose author is on no team, and for legacy runs with no
recorded author — both are admin-only by design.

## 5. Verification

1. `cd moltrace_frontend && pnpm typecheck` — passes against the regenerated schema today.
2. `pnpm vitest components/spectracheck/... --run` for the panel.
3. Backend proof already in place: `tests/test_fid_run_reviewer_visibility.py` (22 tests)
   covers the capability, each negative, the lapse-on-completion, the reviewer-of-record
   clause, the 409 ordering, and both contract fields.
   `tests/test_fid_run_review_separation.py` holds segregation of duties and carries the
   two re-baselined assertions.

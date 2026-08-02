# Frontend handoff — comments, approvals and reviewer nominations

**From:** backend session. **Commits:** `9ca1c69` (comments), `ef25cab` (approvals), `340cc1f` (reviewers).
**Status:** merged to `main`, full suite green (3350 passed).

**This builds directly on work you already finished.** `subject-review-tasks.ts`,
`subject-review-tasks-panel.tsx` and its two mount sites are exactly the pattern these three
follow — same subject pair, same registry, same 404/403 semantics. If you copy that file three
times and change the nouns you will be ~90% right. The rest of this document is the 10%.

---

## Task 1 — Regenerate

```bash
cd /Users/michaelhotor/MolTrace/moltrace_backend && .venv/bin/uvicorn nmrcheck.main:app --port 8000
```
```bash
cd /Users/michaelhotor/MolTrace/moltrace_frontend && npm run generate:openapi
```

| Kind | Name | Note |
|---|---|---|
| New paths | `POST/GET /comments`, `PATCH /comments/{comment_id}` | |
| New paths | `POST/GET /approvals` | **no PATCH** — see below |
| New paths | `POST/GET /reviewers` | **no PATCH** — see below |
| New schema | `SubjectCommentCreate` | `{subject_type, subject_id, comment, comment_type?, metadata_json?}` |
| New schema | `SubjectApprovalCreate` | `{subject_type, subject_id, decision, rationale, approver_email?, metadata_json?}` |
| New schema | `SubjectReviewerCreate` | `{subject_type, subject_id, reviewer_email, status?, metadata_json?}` |
| Changed | `EvidenceCommentRecord`, `ApprovalRecord`, `SessionReviewerRecord` | each gains `subject_type`, `subject_id`, `module`; `session_id` now nullable |

`SubjectReviewTaskCreate` is already in `schema.d.ts` — only these three are new.

**Done when:** `grep -c "SubjectApprovalCreate" src/lib/api/schema.d.ts` is non-zero.

---

## Task 2 — Comments

Straight copy of the review-task pattern. `PATCH /comments/{id}` takes `EvidenceCommentUpdate`;
the field you want is `resolved`, so a comment can be marked settled.

Everything from `subject-review-tasks.ts` carries over unchanged: unreachable subject → **404**
(never "insufficient permissions"), `spectracheck_session` → **403** because sessions keep their
own comment surface, which can additionally anchor a note to a specific piece of evidence.

---

## Task 3 — Approvals *(read the vocabulary note — it will 422 you otherwise)*

An approval is a **sign-off decision**: who decided what, and why. `rationale` is required.

**The trap:** `schema.d.ts` contains *two* approval vocabularies, and they are not
interchangeable.

- `SubjectApprovalCreate.decision` accepts **`approved` | `rejected` | `needs_changes` | `deferred`**.
- `ApprovalRecord.decision` is wider, and also contains `approved_plausible` and
  `approved_confirmed`.

Those last two are **structure-elucidation** language belonging to the SpectraCheck session
surface — they say something precise about a proposed structure and nothing about a regulatory
filing. They appear on the record type only because both surfaces share one table. Sending either
one to `POST /approvals` is a 422.

So: drive the picker from `SubjectApprovalCreate["decision"]`, never from `ApprovalRecord`.

**There is no PATCH.** An approval is a historical record of a decision at a point in time;
changing it after the fact would falsify the audit trail. To change position, record another
approval — the list is ordered oldest-first, so the latest entry is the current one.

**An approval is not a signature.** It records the decision. A §11.70 electronic signature is
created separately through `/esignatures/records` and bound to a point-in-time report
(`spectracheck_report` or `regulatory_readiness_report` are now bindable target types). Don't
label an approval button "Sign" — that would promise a binding this record does not carry.

---

## Task 4 — Reviewer nominations *(the copy matters here)*

`POST /reviewers` records **who is expected to look** at a record.

**A nomination does not grant access.** Access comes from the owning team. Nominating someone
outside the team succeeds and lets them in nowhere — this is deliberate and tested, because an
assignment that silently widened access would be a second, weaker way into a record.

That has a direct consequence for the interface: **do not** word this as "share with", "give
access to", or "invite". It is "request review from" / "nominate a reviewer". If a nominated
person cannot open the record, that is correct behaviour, not a bug — and worth a quiet hint in
the UI rather than a retry.

Note the asymmetry with SpectraCheck: on a *session*, a reviewer row does confer a session role.
So the two surfaces genuinely differ in meaning, and the session one is not a model for this copy.

**There is no PATCH.** Re-posting the same `reviewer_email` for the same subject updates the
existing row in place rather than stacking duplicates, so "change status" is another POST.

---

## Where these go

The two workspaces already hosting `SubjectReviewTasksPanel`:

- `components/regulatory-hub/regulatory-dossier-workspace.tsx`
- `components/reaction-optimization/reaction-project-detail.tsx`

Four panels on one record is a lot of chrome — worth considering a single "Collaboration" section
with tabs rather than four stacked cards, but that is your call.

---

## Verification

With `MOLTRACE_ENABLED_MODULES=spectracheck` the four generic surfaces stay reachable and simply
return nothing, because there are no dossiers or campaigns to address — they are classified
platform, not per-product. That is expected; it is not a gating bug.

**Done when:** on a dossier owned by your team, you can leave a comment and resolve it, record an
approval with a rationale, nominate a reviewer, and see all three survive a reload — with an empty
browser console.

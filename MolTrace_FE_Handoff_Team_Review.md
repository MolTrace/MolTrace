# Frontend handoff — team ownership & subject-addressed review tasks

**From:** backend session. **Commits:** `7d2d33e`, `8b33d0c` (team ownership), `39e7b6f` (review tasks).
**Status:** merged to `main`, full suite green.
**Supersedes nothing** — this is additive to `MolTrace_FE_Handoff_Standalone_Modules.md`, which was
consumed in full.

---

## Why this exists

Regentry filings and Repho campaigns were owned by whoever created them, so a colleague could not
see them at all — a five-person regulatory team had to share one login. They are now owned by the
creator's **team**, and a review task can be raised against a filing or a campaign, not only a
spectroscopy session.

The frontend consequence is in two parts: one contract to consume, and one behaviour change with
no contract at all — which is the kind that slips past a schema diff.

---

## Task 1 — Regenerate the contract

```bash
cd /Users/michaelhotor/MolTrace/moltrace_backend && .venv/bin/uvicorn nmrcheck.main:app --port 8000
```

```bash
cd /Users/michaelhotor/MolTrace/moltrace_frontend && npm run generate:openapi
```

**Contract delta by name:**

| Kind | Name | Note |
|---|---|---|
| New path | `POST /review-tasks` | raise a task against a subject |
| New path | `GET /review-tasks?subject_type=&subject_id=` | the queue for one subject |
| New path | `PATCH /review-tasks/{task_id}` | progress a task |
| New schema | `SubjectReviewTaskCreate` | `{subject_type, subject_id, title, description?, assigned_to?, status?, priority?, metadata_json?}` |
| Changed schema | `ReviewTaskRecord` | gains `subject_type`, `subject_id`, `module`; **`session_id` is now nullable** |

`subject_type` is `"spectracheck_session" | "regulatory_dossier" | "reaction_project"`.

**On the nullable `session_id`:** a task is addressed *either* by `session_id` (the existing
SpectraCheck surface, unchanged) *or* by the subject pair — never both. I checked the existing
consumers before changing it: `src/lib/spectracheck/review-queue.ts` and
`spectracheck-review-collaboration-panel.tsx` read review tasks as `Record<string, unknown>`, so
regenerating should **not** produce type errors. If you later switch those to generated types,
that's where the nullability will surface.

**Done when:** `grep -c "SubjectReviewTaskCreate" src/lib/api/schema.d.ts` is non-zero.

---

## Task 2 — Let a team raise and work a review task

`ReviewTaskRecord.module` names the product (`regulatory_hub` / `reaction_optimization` /
`spectracheck`) so a mixed queue is readable without re-deriving it.

Natural homes:
- **Regentry** — the dossier workspace, alongside the existing review decision.
- **Repho** — the campaign detail view.

```jsonc
// POST /review-tasks
{ "subject_type": "regulatory_dossier", "subject_id": 42,
  "title": "Confirm the nitrosamine limit", "assigned_to": "reviewer@example.com" }
```

**Two behaviours worth designing around, not discovering:**

1. **Unreachable subjects return `404`, not `403`.** A subject that does not exist and one the
   caller may not see are deliberately indistinguishable, so raising a task cannot be used to
   probe whether another customer's filing exists. Do not build an "insufficient permissions"
   state off this — it is a not-found.
2. **SpectraCheck sessions are refused here with `403`.** They keep their richer session-scoped
   surface with per-session reviewer roles. Keep calling
   `/spectracheck/sessions/{id}/review-tasks` for those; do not route them through the generic
   endpoint.

**Done when:** a teammate can raise, see and progress a task on a colleague's dossier, and a user
from another organization gets a not-found state rather than an error toast.

---

## Task 3 — The behaviour change with no contract *(read this one)*

Team ownership changed **what the existing endpoints return**, with no schema delta:

- `GET /regulatory/dossiers` now includes dossiers created by teammates.
- `GET /reaction-projects` now includes campaigns created by teammates.
- Their children follow — action items, notifications, bridges, exports, the mobile queue.

Nothing to regenerate; the risk is **copy and affordances that quietly became untrue**. I checked
the current surfaces and found no "Your dossiers" / "My campaigns" heading and no creator column,
so nothing is misleading today. The things to avoid adding:

- a "mine" framing on either list without an explicit filter behind it;
- an owner/creator column that implies the viewer is the owner;
- anything that assumes the current user can be the only editor.

A dossier or campaign with **no** organization stays creator-only — a user with no team shares
with nobody — so both states exist in the wild and the UI should not assume either.

**Done when:** a second team member signs in and sees the team's filings without any label
claiming they authored them.

---

## Not in this handoff

- **Signable module artifacts** — SpectraCheck evidence reports and regulatory readiness reports
  are becoming content-bindable for §11.70 signatures. That work is still in flight backend-side;
  it adds no new routes (the existing `/esignatures/records` surface is already generic), only new
  valid `target_type` values. I'll hand it off separately once it lands.
- Reviewers, comments, approvals, report locks and share links for Regentry/Repho — still
  SpectraCheck-only. Review tasks are the first slice of that carve-out.

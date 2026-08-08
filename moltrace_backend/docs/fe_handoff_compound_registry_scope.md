# FE handoff — compound registry reads are owner-scoped now

**Backend commit:** `31f16bd`
**Contract:** none. No models changed, `schema.d.ts` needs no regeneration.
**Pages affected:** `app/compounds/[compoundId]/page.tsx`,
`app/compounds/[compoundId]/graph/page.tsx`, and any compound list/search surface

---

## 1. What changed

The compound registry used to be readable by every signed-in user; only writes
were gated. Probed live before the change, a second account could read another
account's `preferred_name`, `registry_id` and `inchikey`, and could find the row
by searching the registry id.

That was a **deliberate, documented decision** — a compound registry is a shared
reference and people do look up structures registered by colleagues. It is the
wrong *default* for a hosted multi-tenant product, where a compound's existence
under a code name is confidential long before its structure is.

So it became a deployment setting rather than a straight reversal:

| `COMPOUND_REGISTRY_VISIBILITY` | reads | writes |
|---|---|---|
| `owner` (**default**) | only what you registered | only what you registered |
| `shared` | the whole registry | only what you registered |

Admins and the system api key see everything in both modes.

## 2. The status codes you will see

**Everything that used to be a 200 for a non-owner is now a 404**, including
child records — structures, aliases, batches, aliquots, relationships, evidence
links, and the knowledge graph.

**The compound `PATCH` moved from 403 to 404** in owner mode. Its old 403 was
justified in a code comment by "the registry is a shared reference and its rows
are readable" — the exact premise this change removes. Left as 403 it would have
confirmed a compound exists at an id the caller cannot read, and compound ids are
sequential.

In `shared` mode the write refusal stays **403**, because the row is readable
anyway and 403 is the more useful answer.

## 3. What to change

1. **Do not render "this compound does not exist" as a hard error page** on
   `app/compounds/[compoundId]/page.tsx`. A 404 there now means *either* the
   compound is gone *or* it belongs to someone else, and the backend will not
   tell you which — that indistinguishability is the point. Copy should be
   neutral: something like "This compound isn't available in your registry."
2. **Distinguish 403 from 404 by status code, never by message.** In owner mode
   an unauthorized edit is a 404; in shared mode it is a 403 whose `detail`
   explains it. Also note the `/api/backend` proxy sanitises all 401/403 bodies,
   so the 403 `detail` may not survive — treat the status as the signal.
3. **Empty lists are now normal, not a bug.** A new user sees an empty registry
   and an empty search. Make sure the empty state reads as "you haven't
   registered anything yet", not "something failed".
4. **Attaching to a compound you don't own is refused too.** `POST` of an alias,
   structure, batch, aliquot, relationship or evidence link against another
   account's compound returns 404 in owner mode (403 in shared). This was closed
   in the same commit — scoping only the reads would have left a stranger able
   to hang records off a compound they could not see, with the 201-vs-404 itself
   confirming the compound existed.

## 4. If a customer needs the old behaviour

It is one environment variable, no code change and no migration:

```bash
COMPOUND_REGISTRY_VISIBILITY=shared
```

Documented in the root `README.md` configuration table. This is the correct
answer for a single-lab deployment where the registry genuinely is a shared
reference — the original design intent, preserved.

## 5. Verify

```bash
cd moltrace_frontend && pnpm vitest app/compounds --run
```

Any fixture that mocks a compound fetch as a bare 200 will keep passing. Add a
case where the fetch returns 404 and assert the page renders the neutral
unavailable state rather than an error boundary.

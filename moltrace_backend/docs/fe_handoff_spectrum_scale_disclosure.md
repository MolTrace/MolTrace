# FE handoff — integrals without a structure are ratios, and now say so

**Backend commits:** `31ccaf2` (structure optional + disclosure), `653b402` (FID review)
**Contract:** `schema.d.ts` **already regenerated and committed** in `31ccaf2`. Do not
regenerate — pull and use it.
**Routes affected that the FE calls today:** `POST /nmr/raw-fid/preview`,
`POST /nmr/raw-fid/process`, `POST /nmr/processed/preview`, `POST /nmr/processed/analyze`

---

## 1. What changed and why it matters on your screens

When no structure is supplied, integrals are scaled so the **smallest resolved
signal = 1 H** and everything else is a multiple of it. The ratios are correct;
the absolute values are not proton counts. Measured on a real 500 MHz spectrum
(validation fixture 33, MeOD), the same five leading peaks:

| | peak 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| with a 6 H structural budget | 0.008 | 0.098 | 0.094 | 1.0 | 0.5 |
| **with no structure** | 1.0 | 14.0 | 13.5 | **123.5** | 84.5 |

Eleven warnings were emitted on that spectrum and **not one of them said so**, so
`123.5H` in the rendered NMR string was indistinguishable from a measurement.

A new warning now appears in `warnings[]` on every response where no structure
grounded the proton budget:

> These integrals are relative. With no structure to set a proton budget, the
> smallest resolved signal is set to 1 H and every other signal is reported as a
> multiple of it, so the values are ratios between signals rather than proton
> counts. Supply a valid structure to scale them to its proton budget.

**Verified live on your routes** — `/nmr/raw-fid/preview` and
`/nmr/raw-fid/process` both emit it with no `candidates_text`, and both stop
emitting it once `candidates_text` is supplied. It is a real condition, not a
permanent banner, so it is safe to render prominently.

## 2. What to change

1. **Surface this warning where the integrals are rendered, not in a generic
   warnings drawer.** It qualifies the numbers on screen; a reader who does not
   see it next to `123.5H` has been told nothing.
2. **When it is present, stop printing the `H` suffix in the UI** — render it as
   "× smallest signal", "rel.", or just the bare ratio. **The frontend is the
   only place this can be fixed, permanently — not just for now.** See §5: the
   backend cannot change the string, and that is settled, not pending.
3. **Prompt for a structure at the point of pain.** The warning names the
   remedy — supplying `candidates_text` (raw-FID routes) or `smiles`
   (processed routes) converts the ratios into proton counts. That is the single
   highest-value nudge on the upload screen.
4. No change needed when a structure is supplied. Behaviour is identical.

## 3. Contract change (low impact, but read it)

`FIDProcessResult.generated_inputs` and `.analysis` are now **nullable**, and the
request body is fully optional, because `POST /raw-fid/{archive_id}/process` no
longer requires `smiles`:

```ts
// schema.d.ts, already updated
FIDProcessResult: {
    preview: components["schemas"]["FIDPreviewReport"];
    generated_inputs?: components["schemas"]["AnalysisInputs"] | null;
    analysis?: components["schemas"]["AnalysisReport"] | null;
};
```

Null means **no structure was supplied, so no verification was performed** — not
an error, and not an empty verdict. A placeholder verdict with nothing to verify
would be a fiction.

The only current caller is `lib/pilot/golden-path.ts:248` (`processRawFid`),
which always sends `smiles` (it is a required golden-path input), so it always
receives non-null and **needs no change**. Its consumer
`nmrTextFromFid` in `lib/pilot/use-golden-path-run.ts` already guards with
`isRecord`, so `pnpm typecheck` is unaffected. This is recorded so the nullability
does not look like an unexplained regression later.

**Newly possible:** the vault route can now process a FID with no structure at
all, which is the auditable path the API's own guidance recommends
(`POST /raw-fid/upload` → `POST /raw-fid/{archive_id}/process`). If you want an
"I don't know what this is yet" flow, that route now supports it.

## 4. Also available, no FE work required

`653b402` opened the four FID review routes (`/fid/runs/{id}/review|approve|
reject|request-changes`) from **admin-only** to **any authenticated user except
the run's creator**. There is currently **no FE surface for these at all**
(grepped: zero references), so nothing breaks. Noted because the capability is
now buildable: a lab reviewer is a senior chemist, not IT.

If you do build it: self-review returns **409** with a specific message
("You created this run, so it needs a review from someone else…"). It is
deliberately not 403 — a 403 would be stripped by the `/api/backend` proxy's
401/403 sanitiser and would read as a broken feature. Render the 409 `detail`.

## 5. Why the backend cannot fix the string — measured, and settled

`inferred_nmr_text` still prints `123.5H`, and it will keep doing so. This was
originally deferred as "blocked on a contended file"; that block is gone
(`c369314` moved the disclosure inside the producers and deleted the AST guard
that stood in for enforcement). The rendering was then attempted properly and
**the parser will not allow it**:

```
"3.65 (q, J = 7.1 Hz), 1.26 (t)"            -> PeakParseError
"3.65 (q, 123.5 rel), 1.26 (t, 84.5 rel)"   -> PeakParseError
```

The parser requires an `NH` integral, and `inferred_nmr_text` is not display-only
— it is fed back in as `AnalysisInputs.nmr_text` (`api.py:7882`, `api.py:12442`)
and re-parsed. Changing the suffix would stop the FID path producing analysable
text at all: a functional regression traded for a cosmetic gain.

So **item 2 is permanent frontend work, not a stopgap.** Teaching the parser a
relative notation would be a core-contract change affecting everything that reads
NMR text, and is its own piece of work if it is ever wanted.

**One hazard you do not need to defend against.** If a user copies ungrounded
text into a structured analysis, the relative numbers are *not* silently accepted
as protons — the validator refuses by name:

```
SMILES / 1H NMR mismatch: the parsed text accounts for 152H,
but the structure expects 6 total H.
```

So the FE job is to stop the number *looking* like a proton count on screen. The
backend already stops it *being used* as one.

## 6. Verify

```bash
cd moltrace_frontend && pnpm vitest components/spectracheck --run
```

Existing fixtures return responses without the new warning, so they will keep
passing while the panel renders nothing new. Add a fixture whose `warnings[]`
contains the disclosure string and assert it renders next to the integrals —
otherwise this ships green and invisible.

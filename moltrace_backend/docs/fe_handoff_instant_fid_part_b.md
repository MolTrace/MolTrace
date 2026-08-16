# FE handoff — Instant FID, Part B

**Backend commits:** `1e8982c` (Part A: threadpool, persisted report cache, redundant-compute
removal, honest presets, gzip) and the follow-up that softened the preset refusal copy.
**Owner after this doc:** a frontend-scoped session.
**Source of truth for scope:** `MolTrace_Prompt_2_Instant_FID.md` Part B (repo root, untracked).

## 0. What changed underneath you, and what it unblocks

Part A landed on 2026-08-15. Three of its effects change what the frontend should do:

1. **The server no longer executes the FID pipeline on its event loop.** Every async raw-FID
   route now runs the compute in a threadpool, so concurrent requests stop queueing behind each
   other. The measured 40–78 s contention mode is gone. This is the precondition B2 was waiting
   on.
2. **A repeat of any (archive, settings) pair is served from a persisted cache** — ~0.09 s, and
   it now survives a restart and crosses instances, where before it was a per-process accident.
3. **Processing presets do what their labels say, and unknown ids are refused.** Before, all four
   product preset ids were unknown to the resolver, silently collapsed to "balanced", and
   produced byte-identical settings — "No baseline correction" still ran Bernstein baseline and
   auto-phase.

Measured before/after is in `moltrace_frontend/docs/raw_fid_latency_be_handoff.md` §6.

## 1. Directory

```bash
cd moltrace_frontend
```

## 2. Regeneration — NOT required

`schema.d.ts` was already regenerated and committed as part of `1e8982c`. No backend route
signature or model changed after that, so **do not regenerate as a prerequisite**. Verify what
you have rather than assuming:

```bash
grep -n 'phase_preserve' src/lib/api/schema.d.ts
```

One hit at the `FIDProcessingPreset` id union means your contract is current.

## 3. Contract delta, by name

| Name | Change |
|---|---|
| `FIDProcessingPreset.id` union | gained **`phase_preserve`** (six members now: `baseline_preserve`, `phase_preserve`, `balanced`, `sensitive_weak_peaks`, `higher_resolution`, `custom`) |
| `Body_raw_fid_archive_preview_…` and `Body_raw_fid_archive_process_…` | ten recipe fields changed from required-with-default to **optional-nullable**: `apodization_mode`, `apply_group_delay`, `auto_phase`, `auto_baseline`, `phase_mode`, `phase_p0`, `phase_p1`, `baseline_correction`, `baseline_order`, `mask_solvent_regions` |

**Why the second one matters:** omitting a field now means "the preset decides". Sending a value
marks that axis as an explicit caller override, which suppresses the 1H advised-processing
recipe on that axis. Sending `phase_mode: "auto"` to be polite would silently defeat the
"No phase correction" preset. **Send the preset and omit the recipe fields** unless the user
explicitly set a control.

### Preset id mapping (what the backend now does with each)

| id the FE sends | resolves to | behaviour |
|---|---|---|
| `safe_automatic` | `balanced` | auto phase + Bernstein baseline |
| `no_baseline_correction` | `baseline_preserve` | auto phase, **no baseline correction** |
| `no_phase_correction` | `phase_preserve` | **no phase correction**, Bernstein baseline |
| `imported_parameters` | — | **rejected, HTTP 422** — no engine support exists |

## 4. Item B4 — preset UI truth (do this first; it is a live break)

`imported_parameters` is still offered in the picker and is put on the wire unmapped
(`fd.append("processing_preset", settings.preset)`, `spectracheck-raw-fid-section.tsx:908`), so
a user choosing it now gets an error where they previously got silent, wrong "balanced"
processing. It is duplicated in two hand-written places and **both must change together** — the
union feeds sessionStorage rehydration, so removing only the picker entry lets a saved session
restore the dead value:

1. `components/spectracheck/spectracheck-raw-fid-section.tsx:160` — the
   `{ value: "imported_parameters", label: "Imported parameters" }` entry in `PRESETS`
   (array at `:158-163`, rendered into the `<select id="raw-preset">` at `:1997-2007`).
2. `components/spectracheck/spectracheck-tab-state-context.tsx:36` — the `"imported_parameters"`
   member of the `RawFidPreset` union (declared `:34-38`). Add a rehydration guard that drops an
   unrecognised stored preset instead of restoring it.

Then:

3. **Error copy.** The backend refuses with `422` and this body shape:
   ```json
   { "detail": "The processing preset 'imported_parameters' is not one this analysis offers. Choose a different processing preset.",
     "code": "unknown_processing_preset" }
   ```
   `detail` is already human and safe to render verbatim — it names no preset ids, no endpoint,
   no status code. **Branch on `code`, never on the sentence.** If you render your own copy
   instead, use the label the user picked, not the id.

   **Known gap, your call whether to close it.** The refusal deliberately does not list the
   alternatives, and the contract does not fully enumerate them either: `processing_preset` is
   typed `string | null` (not an enum) on every request body, and `GET /fid/presets` publishes
   only the six *canonical* ids — not the product aliases the picker actually sends
   (`safe_automatic`, `no_baseline_correction`, `no_phase_correction`). So the accepted input
   set is wider than anything a client can read from the contract. Today the FE hardcodes its
   own list, which is exactly why `imported_parameters` drifted out of sync in the first place.
   If you want the picker driven by the server instead of a constant, say so and the backend
   will widen `GET /fid/presets` to publish its aliases — that is a contract change, so it
   belongs with the frontend work that consumes it rather than ahead of it.
4. **`Auto-FT preview · {autoPreviewPreset}`** at `:2435` renders a raw id (`balanced`). Map it
   to a label before display.
5. Re-check `tests/visual-baseline/integration-spectracheck-uploads.ts:312`, which references the
   preset control.

## 5. Item B1 — stop re-uploading the archive for process

`runProcess` (`spectracheck-raw-fid-section.tsx:1071-1096`) still posts the whole archive:
`buildFormData(file, true)` at `:1085` → `apiFetch("/nmr/raw-fid/process", …)` at `:1086`.
`buildFormData` unconditionally appends the bytes (`fd.append("file", file)`, `:902`); its
`withProcess` flag only toggles preset/`preserve_raw`, so **no bytes-free body exists yet** —
you have to add one.

The archive id is already computed during preview (`previewArchiveId = extractRawArchiveId(data)`,
`:1046`) but is scoped to a local declared at `:1036` that only `runPreviewSpectrum` consumes at
`:1054`. `runProcess` never reads it — the pieces are adjacent, which is why this reads as done
at a glance and is not.

1. When `extractRawArchiveId(previewResult)` is non-null, call
   `POST /raw-fid/{archive_id}/process` with form fields only. That route loads the bytes from
   the vault; the current shape crosses the wire twice and re-runs 4 hash passes + 2 disk reads
   server-side.
2. Add a bytes-free body builder (or a third mode to `buildFormData`) emitting `sample_id`,
   `solvent`, `nucleus`, `processing_preset`, `preserve_raw` and the shared session guidance —
   **without** the recipe fields (see §3).
3. Keep the upload path as fallback, and decide the fallback trigger explicitly: catch the
   404/410 from a stale or aged-out archive id and retry once via upload, so a vaulted archive
   that expired does not surface as a hard failure.
4. Same for the batch runner `runBatchItems` (`:1109-1142`): it picks between
   `/nmr/raw-fid/process` and `/nmr/raw-fid/preview` at `:1136` and passes
   `buildFormData(step.file, …)` at `:1139`, so a scan-then-process pass uploads every archive
   twice. A row that completed in scan mode holds its preview payload in `item.result` — take the
   archive id from there.

Note `src/lib/spectracheck/raw-fid-batch.ts` contains **no** request-building code (zero
`apiFetch`, zero `FormData`); it is types and admission rules. All the request shaping lives in
the root component.

There is a working example of the archive-scoped call already in the codebase:
`lib/pilot/golden-path.ts:248`.

**Before wiring, check the accepted form fields against `schema.d.ts`.** A key the Pydantic model
rejects under `extra=forbid` gives a 100% 422 rate; diagnose by A/B-posting to a nonexistent
archive id — 422 means bad shape, 404 means the shape was valid.

## 6. Item B2 — batch fan-out

The fan-out is a sequential `for (const step of plan)` at `spectracheck-raw-fid-section.tsx:1118`
with an awaited `apiFetch` in the body. The rationale it cites — that the work "happens inline on
the server's request loop" — **is now factually wrong**, and it exists in three places, not the
one the prompt listed:

1. `src/lib/spectracheck/raw-fid-batch.ts:9-16` (framed at `:9` as "not negotiable")
2. `components/spectracheck/spectracheck-raw-fid-section.tsx:1099` (the "ONE DATASET AT A TIME" block comment)
3. user-visible copy at `components/spectracheck/spectracheck-raw-fid-batch.tsx:352`:
   *"Running several at once would not make them finish sooner."*

Whether or not you raise the concurrency, **all three must state the current reason** — leaving
one is the half-applied-guard shape that has bitten this repo before.

If you do raise it: the prompt suggests starting at 3, but 3 is a round number, not a measured
operating point — measure against a local backend and pick from the data, per the repo's
bounds-from-data rule. The memory-bound step is archive extraction. Also replace the single
`controller: AbortController | null` slot on `RawFidBatchRunHandle` (`raw-fid-batch.ts:121`) with
per-item controllers and re-check `stopRawFidBatchRun` / `abortRawFidBatchRun` (`:187-205`),
which today abort exactly one in-flight request.

**Two tests encode the old behaviour and will fail. Re-baseline them visibly, with the reason:**
`components/spectracheck/spectracheck-raw-fid-batch.test.tsx:168` ("analyzes every dataset, ONE AT
A TIME") and `:542` ("says why datasets run one at a time").

## 7. Item B3 — proxy: stream uploads, bound the wait honestly

`app/api/backend/[...path]/route.ts` is the only backend proxy (189 lines; the sole `route.ts`
under `app/api/backend/`).

1. `:100` is `body: hasBody ? await request.arrayBuffer() : undefined` — the whole archive is
   buffered into the function heap and upload time is client→proxy **plus** proxy→backend,
   summed. Forward `request.body` with `duplex: "half"` in the fetch init (currently `:97-103`;
   there is no `duplex` key today).
2. Add an explicit size guard that returns a readable error. `content-length` is currently
   stripped as hop-by-hop in the delete loop at `:79-83` — read it *before* that.
3. Add `export const maxDuration` sized to the measured p99 of the process call. The only
   route-segment config today is `export const dynamic = "force-dynamic"` at `:34`, and
   `next.config.mjs` / `vercel.json` set no body limit or duration.
4. Align `RAW_FID_MAX_ARCHIVE_BYTES` (`src/lib/spectracheck/raw-fid-batch.ts:32`, advertising
   2 GiB) with the real platform ceiling, taking the stricter of that and the backend's
   `raw_archive_max_bytes`, so the preflight refuses locally instead of surfacing a platform 413.
5. **Keep** the 504 → "unconfirmed" branch (`raw-fid-batch.ts:369-376`) until measurement shows
   the ceiling is no longer hit. Do not delete it in the same change that adds `maxDuration`.

## 8. Verification

```bash
pnpm typecheck && pnpm lint && pnpm vitest --run
```

No test covers any of the four Part B behaviours today, and two pin the opposite. Add:

- **B1:** after a preview whose response carried `metadata.raw_archive_id`, the process call goes
  to `/raw-fid/{id}/process` and its body has **no** `file` field. Re-baseline
  `components/spectracheck/spectracheck-preview-rendering.test.tsx:796`, which currently asserts
  the call lands on `/nmr/raw-fid/process` (its preview fixture already carries
  `metadata.raw_archive_id`, so it is the right test to flip), and the batch assertion at
  `spectracheck-raw-fid-batch.test.tsx:201`, which reads `body.get("file")` to assert bytes are
  present on every call.
- **B2:** the new concurrency bound is respected (and the two tests above, re-baselined).
- **B3:** the proxy forwards a stream rather than a buffer; the size guard returns the readable
  error; oversize is refused client-side by the preflight.
- **B4:** `imported_parameters` is absent from the picker **and** from the rehydration path; a 422
  with `code: "unknown_processing_preset"` renders human copy.

Report before/after wall-clock for cold preview, warm process, and a batch of 3 — the backend
numbers to compare against are in `raw_fid_latency_be_handoff.md` §6.

## 9. Out of scope

No queue infrastructure (deliberately deferred). No changes to vault ingest/verify hashing on the
upload path — B1 avoids re-triggering it rather than weakening it. No science-threshold changes.

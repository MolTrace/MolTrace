# FE→BE handoff — raw-FID analysis latency

**From:** frontend session · **Scope:** measurement + the FE-side fixes already shipped, and the
one item that is genuinely backend work.

The user reported "spectrum generation and processing/analysis takes too long for the raw FID".
Everything below was measured against the live backend on `localhost:8000` with a real Bruker
folder (75 files, 3.5 MB zip). The sample is not named here — real sample
identities are not published, and no number below depends on which one it was.

## 1. The headline number, and a correction worth reading

An early measurement suggested 0.67 s and led the FE session to conclude the server was not the
bottleneck. **That was wrong — it was a cache hit.** `process_bruker_1d_zip` is memoized
(`fid.py`, LRU capped at 32 entries) and the same archive had already been processed earlier in
the session. Re-measured with genuinely novel cache keys:

| Case | Wall time |
|---|---|
| First analysis of a new spectrum (novel key) | **5.0 – 5.9 s** |
| Same spectrum **with `candidates_text` (a SMILES)** | **11.8 s** |
| Repeat with identical parameters (memo hit) | 0.25 – 0.48 s |
| Client-side zip of the folder (FE, fflate, 75 files) | 0.17 s |
| Upload (localhost) | 0.01 s |
| Response payload | 447 KB (83 % is `x`/`y`, 9 692 points each) |

So the server-side compute **is** the dominant cost on a first-time analysis, and supplying a
structure roughly **doubles** it.

**The ask:** the ~6 s delta between "no guidance" and "with `candidates_text`" is the single
biggest item on this path. Worth profiling what the guidance route adds — expected-H derivation
from the candidate SMILES (`api.py` ~10645) and whatever it triggers downstream — before any
further FE work is justified.

Secondary: the 32-entry LRU means routine use evicts entries quickly, so real users will hit the
5–12 s cold path far more often than a dev re-running one file.

## 2. Already fixed FE-side (no backend action needed)

- **Job polling was a flat 2 s grid** → replaced with a backoff ladder
  (cumulative `0 · 250 · 500 · 1000 · 2000 · then 2000 ms`). It deliberately lands on 2000 ms so it
  can never discover a job later than the old interval did. Commit `0996e58`.
  *Note this affects the **processed-spectrum** tab, whose job types are implemented — not raw FID,
  see below.*
- **Each poll made two sequential requests** (`/jobs/{id}` then `/jobs/{id}/events`) → now parallel.
- **Elapsed-seconds counter** on the raw-FID Preview/Process buttons, so a 6–12 s synchronous wait
  visibly ticks instead of reading as a hang.

## 3. A dead path we removed — please confirm the intent

The raw-FID tab had **"Background job · Preview/Process"** buttons. `SUPPORTED_JOB_TYPES` includes
`nmr_raw_fid_preview` / `nmr_raw_fid_process`, but `_execute_job` (`orchestration_store.py`) has no
branch for them and falls through to *"registered, but its synchronous execution adapter is not
implemented yet."* `create_analysis_job` catches that, marks the row `failed`, and still returns
200 — so the job was **born dead, 100 % of the time**, after uploading the whole archive to
`/files/upload`.

Reproduced live:

```
POST /jobs {"job_type":"nmr_raw_fid_process"}
  -> status: failed
  -> "Job type 'nmr_raw_fid_process' is registered, but its synchronous execution adapter is not
      implemented yet."
```

The FE entry point is now disabled with an honest label and the dead handlers removed (commit
`272a2bb`). **If an adapter is planned, tell us and we will restore it** — the code is in git
history. If not, consider dropping those two entries from `SUPPORTED_JOB_TYPES` so the server
stops accepting jobs it cannot run.

## 4. Blocked on backend: cluster-splitting

Reported as "the engine can now answer but isn't yet wired to". Confirmed — there is **no HTTP
surface**: a scan of the live `/openapi.json` finds zero occurrences of `cluster_split`,
`split_cluster`, or `cluster_splitting`, and no route whose path contains `cluster` or `split`.

The FE cannot consume it until it is emitted somewhere. When it is wired, the useful contract for
us is the same additive-payload shape used elsewhere: put it on the existing analyze/process
response rather than a new endpoint, and we will read it defensively. Please state the field name,
the shape, and whether it is per-peak or per-cluster.

## 5. Not verified: deployed performance

All numbers here are **localhost**. On Cloud Run, transferring the 447 KB payload and cold-start
latency will add time we cannot see from here. If the complaint persists after the above, the next
measurement should be taken against the deployed backend, not local.

---

## 6. Backend response — Instant FID landed (2026-08-15)

Everything in §1 was re-measured after the Prompt 2 backend work. Numbers below are the same
dev-class M-series Mac, measured on a public 94k-point 1H nmrshiftdb2 fixture (real archives are
never named or committed; the shape matches §1's archive after zero-fill). "Guided" = with
`candidates_text` SMILES, the expensive path from §1.

| Case | Before (this fixture) | After | What changed |
|---|---|---|---|
| Cold, guided (SMILES supplied) | 9.4 s | **4.34 s** | one shared detection preamble for the 7-candidate sensitivity sweep + deconvolve pass; baseline estimated once instead of 7×; debug-only preserved-state QA gated; vectorized trace build |
| Cold, unguided | ~5–6 s | **3.82 s** | same, minus the sweep |
| Repeat, same instance (L1) | 0.017 s | **0.022 s** | unchanged in-process dict |
| Repeat, after restart / other instance (**new**) | full recompute | **0.094 s** | reports now persist in `raw_fid_report_cache` (Alembic 0048); any instance serves any previously computed (archive, settings) pair |
| Concurrent requests | 40–78 s (event loop frozen) | no interference | `process_bruker_1d_zip` now runs in the threadpool on every async route; `/health` answers mid-process (pinned by `test_raw_fid_event_loop.py`) |
| Preview body on the wire | 377–650 KB | ~5–8× smaller | `GZipMiddleware(minimum_size=1024)`; your proxy already decodes |

The §1 ask — "profile what the guidance route adds" — resolved: the doubling was the
structure-guided sensitivity sweep re-running the full detector 7× plus a deconvolution pass.
The sweep now shares one preprocessed trace; its *decisions* are unchanged (all 19 pinned
fixture goldens in `test_fid_pipeline_invariants.py` match bit-identically).

Measured and deliberately **not** taken, per the output-invariance rule:

- Scoring auto-phase on a decimated spectrum: chosen (p0, p1) drift up to 34°/992° vs the
  full-resolution optimum on the 22-fixture corpus — fails display precision, so both
  optimizers still run at full resolution (~1.2 s of the cold run).
- Running the sensitivity sweep on a decimated trace: the chosen sensitivity changes on
  1/8 (stride 2) to 5/8 (stride 5) of guided fixtures — rejected for the same reason.

Also in this change, relevant to Part B (FE) work:

1. **A1 landed** → the one-at-a-time batch fan-out reason in `raw-fid-batch.ts:12-18` is gone;
   B2's measured-concurrency raise is now unblocked.
2. **Presets are honest and strict** (contract regenerated): `safe_automatic`,
   `no_baseline_correction`, `no_phase_correction` map to real behaviours
   (`balanced` / `baseline_preserve` / the new `phase_preserve`); the recipe form fields on
   `/raw-fid/{archive_id}/preview|process` are now optional-nullable ("not sent" = preset
   decides). **`imported_parameters` is rejected with a 422 naming the id** — there is no
   engine support for reading vendor processing parameters, so the option must come out of
   the picker (B4) rather than silently running "balanced".
3. `wall_ms` audit telemetry (Prompt 1) is emitted on all four raw-FID routes, so the
   before/after above is verifiable from ops metrics, not just this table.

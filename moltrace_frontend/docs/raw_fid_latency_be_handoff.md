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

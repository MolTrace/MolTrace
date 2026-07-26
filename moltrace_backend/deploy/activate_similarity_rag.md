# Activating spectral-similarity retrieval + retrieval-augmented reasoning

Runbook for turning on the two SpectraCheck candidate-tool surfaces that ship disabled:

1. **Spectral-similarity retrieval** — gated on `MOLTRACE_SIMILARITY_INDEX` (+ optional
   `MOLTRACE_SIMILARITY_METADATA`) pointing at a FAISS index **file the container can read**.
2. **Retrieval-augmented structure reasoning** — needs (1) **plus** the `anthropic` package in the
   image and an `ANTHROPIC_API_KEY` (model `claude-opus-4-8`).

Three phases, each independently shippable. Written 2026-07-25 from a code-grounded investigation;
citations are `path:line` at that date.

**Key facts up front**

- `faiss-cpu` is a **core** dependency (`pyproject.toml:21`) — retrieval needs **no image rebuild**.
- The env vars take **local file paths**, not `gs://` URLs (`api.py:8003-8024`). On Cloud Run the
  index is delivered via a **cloud-storage (gcsfuse) volume**, not an image bake (see Phase 1 §7).
- The build CLI writes exactly two artifacts: `<out>.faiss` **and** `<out>.faiss.ids.json`.
  `SpectrumIndex.load` auto-derives the sidecar path (`scoring.py:338-351`); the env var points
  **only** at the `.faiss`, and the sidecar must live next to it.
- `anthropic>=0.40` is declared in the optional **`rag`** extra and already resolved in `uv.lock`;
  the deployed image installs only `--extra fid --extra gcs` (`Dockerfile:30,34`), so the reasoner
  requires a Dockerfile change + rebuild.
- **Licensing is the sharpest edge.** An index derived from NMRShiftDB2 is a **CC-BY-SA
  (ShareAlike) derivative** — never commit it, never bake it into a distributed image (`NOTICE`,
  `scoring.py:29-37`). The commercial-safe base is **SimNMR-PubChem (MIT, HF
  `yqj01/SimNMR-PubChem`)** — and it stays MIT **only** if you use its own simulated shifts: the
  `{id, smiles}` build path re-predicts shifts through the NMRShiftDB2-derived HOSE fallback
  (`nmrnet_wrapper.py:58`) and would re-taint the corpus. Use `{id, shifts_1h, shifts_13c}`.

---

## Phase 0 — Local smoke test (verified working 2026-07-25)

Build a tiny index from the in-repo NMRShiftDB2 test fixture and light the retrieval surface up on
localhost. All artifacts land in `spectrum_similarity_index/`, which is gitignored
(`.gitignore:77`) — satisfying the CC-BY-SA never-commit rule.

```bash
cd moltrace_backend && mkdir -p spectrum_similarity_index && uv run python - <<'PY'
import json, pathlib
man = json.loads(pathlib.Path("tests/fixtures/nmrshiftdb2/expected/nmrshiftdb2_bruker_20.json").read_text())
out = pathlib.Path("spectrum_similarity_index/corpus.jsonl")
with out.open("w", encoding="utf-8") as fh:
    for fx in man["fixtures"]:
        rec = {"id": f"nmrshiftdb2:{fx['spectrum_id']}"}
        rec["shifts_1h" if fx["nucleus"] == "1H" else "shifts_13c"] = fx["reference_peak_ppm"]
        fh.write(json.dumps(rec) + "\n")
print("corpus records:", sum(1 for _ in out.open()))
PY
```

```bash
cd moltrace_backend && uv run python scripts/build_similarity_index.py \
  spectrum_similarity_index/corpus.jsonl spectrum_similarity_index/spectra.faiss --ef-construction 200
```

Then point the backend at it and restart:

```bash
export MOLTRACE_SIMILARITY_INDEX="$PWD/spectrum_similarity_index/spectra.faiss"
```

Verification (done 2026-07-25): 19 records → `spectra.faiss` (24 KB, dim=256) +
`spectra.faiss.ids.json`; `SpectrumIndex.load` + a 7-peak ¹H query returned ranked neighbours
(`nmrshiftdb2:40255417` @ L2 6.67). `search(query, k)` — the k is positional (`scoring.py:300`).
In the UI, the SpectraCheck "Spectral-similarity retrieval" panel replaces the "Retrieval index
not configured" empty state once the backend restarts with the env var set.

Notes:
- Retrieval needs **no** metadata sidecar and **no** `anthropic`.
- `encode_spectrum` tolerates an empty nucleus half (`scoring.py:113`), so single-nucleus fixture
  rows encode fine.
- This is a 19-spectrum smoke corpus — a plumbing test, **not** a meaningful precedent database.

### Optional: smoke the reasoner locally

`_reasoning_llm_available` gates on `anthropic` importable **and** `ANTHROPIC_API_KEY` set
(`api.py:8087-8101`):

```bash
cd moltrace_backend && uv sync --extra rag   # also pulls openai (bundled in the extra, unused)
export ANTHROPIC_API_KEY=sk-ant-...          # your key — never commit it
```

Caveat: fixture ids (`nmrshiftdb2:40255417`) are **not** SMILES. Without a
`MOLTRACE_SIMILARITY_METADATA` sidecar mapping id → SMILES, the reasoner treats each id **as** a
SMILES and analogue grounding fails. A real reasoning smoke needs SMILES per id (extractable from
`tests/fixtures/nmrshiftdb2/source/*.nmredata.sd`). Each `/spectrum/reason` call makes up to
**2 × `claude-opus-4-8`** requests — keep `top_k` / `max_candidates` tiny.

---

## Phase 1 — Production retrieval

### 1. Corpus + license decision

- Base: **SimNMR-PubChem** (MIT; re-confirm the dataset card at ship time per `NOTICE`).
- **Curate a subset.** A full 106M-molecule HNSW index is ~130+ GB in RAM and does not fit Cloud
  Run; a ~45k-vector dim-256 index is ~60 MB and fits comfortably. Pre-filter to the relevant
  chemical space.
- SimNMR's own prebuilt Faiss is **not** drop-in (different encoding, no MolTrace ids sidecar) —
  re-encode via `build_similarity_index.py`.

```bash
uv pip install -U 'huggingface_hub[cli]'
huggingface-cli download yqj01/SimNMR-PubChem --repo-type dataset --local-dir ./simnmr_pubchem
```

(Processed LMDB is ~373 GB — use a high-disk VM, not Cloud Run.)

### 2. Convert LMDB → JSONL (shifts-directly path)

⚠️ **UNCONFIRMED:** the LMDB record schema (key names, value codec) is not documented on the
dataset card — read the NMR-Solver reader (github.com/YongqiJin/NMR-Solver) first. Template:

```python
import lmdb, json, pickle, pathlib
env = lmdb.open("./simnmr_pubchem/<lmdb_dir>", readonly=True, lock=False, subdir=True)
out = pathlib.Path("corpus_store/simnmr.corpus.jsonl"); out.parent.mkdir(exist_ok=True)
with env.begin() as txn, out.open("w", encoding="utf-8") as fh:
    for k, v in txn.cursor():
        rec = pickle.loads(v)                      # CONFIRM codec
        fh.write(json.dumps({"id": rec["inchikey"],        # CONFIRM field names
                             "shifts_1h": rec["shifts_1h"],
                             "shifts_13c": rec["shifts_13c"]}) + "\n")
```

Use SimNMR's **own simulated shifts** — never the `{id, smiles}` re-prediction path (HOSE re-taint,
see top). `corpus_store/` and `*.corpus.jsonl` are gitignored.

### 3. Build offline + upload

```bash
cd moltrace_backend && uv run python scripts/build_similarity_index.py \
  corpus_store/simnmr.corpus.jsonl spectrum_similarity_index/spectra.faiss --ef-construction 200
```

```bash
# Bucket: verify it exists first — it is NOT created anywhere in-repo (UNCONFIRMED).
gcloud storage buckets describe gs://moltrace-model-weights --project moltrace-prod || \
gcloud storage buckets create gs://moltrace-model-weights --location=us-central1 \
  --uniform-bucket-level-access --public-access-prevention --project moltrace-prod
```

```bash
# BOTH files must land in the same prefix (load() derives <path>.ids.json).
gcloud storage cp spectrum_similarity_index/spectra.faiss \
  spectrum_similarity_index/spectra.faiss.ids.json \
  gs://moltrace-model-weights/spectrum_similarity/ --project moltrace-prod
```

Do **not** use `moltrace-raw-vault` (public-access-prevention raw-FID vault; different purpose).

### 4. Mount + env var (one revision, no rebuild)

```bash
gcloud run services update moltrace-backend --region us-central1 --project moltrace-prod \
  --add-volume=name=similarity,type=cloud-storage,bucket=moltrace-model-weights,readonly=true \
  --add-volume-mount=volume=similarity,mount-path=/gcs \
  --update-env-vars=MOLTRACE_SIMILARITY_INDEX=/gcs/spectrum_similarity/spectra.faiss
```

- gcsfuse presents the bucket at `/gcs`, so the prefix appears at `/gcs/spectrum_similarity/`.
- The runtime SA (`moltrace-run@`) already has project-wide storage access
  (`deploy/README.md:120-124`) — no new IAM. (Live IAM state UNCONFIRMED — check.)
- No commas in the value, so the `^|^` delimiter isn't needed.
- This service config **survives CI's image-only redeploys** (`ci-cd.yml` deploys `--image` only).
- **Why not image-bake:** `*.faiss` is gitignored, so CI's git-checkout rebuild would silently ship
  an image *without* the file; it would also embed a licensed derivative in a distributed image.
  Also note **neither `.dockerignore` nor `.gcloudignore` excludes `*.faiss`** — a local
  `gcloud builds submit` from a tree containing an index would upload it. Avoid.

### 5. Verify

```bash
curl -s -X POST "$(gcloud run services describe moltrace-backend --region us-central1 \
  --project moltrace-prod --format='value(status.url)')/spectrum/retrieve" \
  -H 'content-type: application/json' -d '{"smiles":"CCO","top_k":5}'
```

Expect `index_available=true` + neighbours (add the service's auth headers; exact request-body
shape UNCONFIRMED — check the OpenAPI). `false` ⇒ wrong mount/env path or missing `.ids.json`.
First post-cold-start call pays a one-time gcsfuse read; then cached by path+mtime
(`api.py:8016-8023`).

---

## Phase 2 — Production reasoner (only after Phase 1)

1. **Dockerfile** — add `--extra rag` to **both** `uv sync` lines (30 & 34; both, or the layer
   cache serves an image without `anthropic`). No re-resolve needed — `anthropic` is already in
   `uv.lock`. No code change: the reasoner call shape already matches `claude-opus-4-8`
   (`rag.py:719-759`). Fix the stale "undeclared dependency" wording in `README.md:147/266` and
   `rag.py:46` in the same change.
2. **Secret** (operator pastes the key themselves):
   ```bash
   printf '%s' 'sk-ant-REPLACE' | gcloud secrets create ANTHROPIC_API_KEY \
     --project=moltrace-prod --replication-policy=automatic --data-file=-
   ```
   (exists already ⇒ `gcloud secrets versions add`). Belt-and-suspenders IAM:
   ```bash
   gcloud secrets add-iam-policy-binding ANTHROPIC_API_KEY --project=moltrace-prod \
     --member=serviceAccount:moltrace-run@moltrace-prod.iam.gserviceaccount.com \
     --role=roles/secretmanager.secretAccessor
   ```
3. **Rebuild + deploy** — preferred: commit the Dockerfile change and let CI (WIF) rebuild+deploy.
   The CI deploy is image-only and preserves the Phase-1 volume + env vars.
4. **Wire the secret + cost guard** — `--update-secrets` (merge), never `--set-secrets` (replace —
   would drop `DATABASE_URL`/`API_KEY`):
   ```bash
   gcloud run services update moltrace-backend --project=moltrace-prod --region=us-central1 \
     --update-secrets=ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest \
     --update-env-vars=RATE_LIMIT_ENABLED=true
   ```
5. **Verify** — `POST /spectrum/reason` returns `index_available=true` **and**
   `reasoner_available=true`. `reasoner_available=false` with the index up ⇒ key or package
   missing (fail-safe degradation to retrieval-only, HTTP 200).

**Cost:** `claude-opus-4-8` at $5/$25 per MTok; ≤ 2 calls/request (initial + one schema retry),
`max_tokens` 16000. Caller knobs: `top_k` (default 50), `max_candidates` (default 5, cap 20). The
built-in per-tenant limiter (300/min when `RATE_LIMIT_ENABLED=true`) is loose for an Opus
endpoint — a tighter dedicated policy is a backend change worth considering.

---

## Validation / change-control notes

- Retrieval (Phase 1) is deterministic nearest-neighbour precedent — low change-control tier.
- The reasoner is verifier-arbitrated decision-support: the deterministic verifier is the sole
  pass/fail arbiter, the hallucination guard drops ungrounded candidates pre-verification, and
  model `self_confidence` is never the prior. Pass/fail authority is unchanged by enablement.
- **Known Part-11 provenance gap:** `/spectrum/reason` calls `propose_structures` **without**
  `audit_recorder`/`audit_user_id` (`api.py:8892-8897`), so the exact prompt + raw completion are
  not persisted to the signed audit chain (only a compact `spectrum.reason` event is). If durable
  model-I/O provenance is in scope, schedule that backend change alongside enablement.
- Change-control package should pin: model id, corpus/index provenance + license attestation,
  image SHA + env-var diff, `tests/test_ai_rag.py` evidence, and a live smoke test.
- Activating these surfaces is a **capability change**: refresh the six white papers + root README
  in the same task (standing docs rule).
- The `MOLTRACE_SIMILARITY_METADATA` sidecar is **hand-authored** (no script emits it). Shape:
  JSON object `id -> bare-SMILES-string` **or** `id -> {smiles, license, shift_summary,
  multiplet_summary, source}`. Retrieval ignores it; the reasoner needs it whenever ids aren't
  bare SMILES.

## Unconfirmed at time of writing (verify before relying)

1. `moltrace-model-weights` bucket existence (never referenced in-repo).
2. SimNMR-PubChem LMDB record schema/codec (read the NMR-Solver reader first).
3. Live Cloud Run env/IAM state (investigation was read-only).
4. Exact `/spectrum/retrieve` + `/spectrum/reason` request-body shapes (check OpenAPI).

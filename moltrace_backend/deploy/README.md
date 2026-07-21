# MolTrace backend — GCP deploy (free-tier first)

Container + build files live one level up: [`Dockerfile`](../Dockerfile),
[`.dockerignore`](../.dockerignore), [`.gcloudignore`](../.gcloudignore),
[`cloudbuild.yaml`](../cloudbuild.yaml). Local/eval stack:
[`docker-compose.dev.yml`](docker-compose.dev.yml).

## First: what "free tier" actually covers

GCP has **two** distinct "free" things — they are not the same:

| | What it is | Good for |
| --- | --- | --- |
| **$300 free trial credit** | 90 days of credit against **any** service | Trialling the *real* managed architecture (Cloud Run + Cloud SQL + Memorystore) at $0 out of pocket |
| **Always Free** | Perpetual, usage-capped, **only some** services | A genuinely $0/mo dev/eval setup |

**Always-Free reach for this backend** (us-central1 / us-west1 / us-east1):

| Service | Always Free | Fits us? |
| --- | --- | --- |
| Cloud Run | 2M req, 180k vCPU-s, 360k GiB-s, 1 GiB egress /mo | ✅ **if scale-to-zero** (`--min-instances 0`). A warm `min-1` instance blows the vCPU-seconds cap. |
| Artifact Registry | 0.5 GB storage | ✅ one small image |
| Cloud Build | 120 build-min/day | ✅ |
| Cloud Storage | 5 GB-mo regional + limited egress | ✅ small vault/weights |
| Secret Manager | 6 versions + 10k access/mo | ✅ |
| Compute Engine | 1× **e2-micro** (1 GB) + 30 GB disk | ⚠️ can host Postgres/Redis/worker, but 1 GB is tight |
| **Cloud SQL** | **none** | ❌ cheapest `db-f1-micro` ≈ $8–10/mo |
| **Memorystore** | **none** | ❌ cheapest ≈ $35/mo |

### Bottom line — two honest free paths

- **Path A — $300 credit (recommended for a real eval).** Run the full managed
  stack for 90 days free: Cloud Run (scale-to-zero) + Cloud SQL `db-f1-micro` +
  Memorystore 1 GB. Follow the main runbook; just add `--min-instances 0`.
- **Path B — true $0/mo (dev-grade).** Cloud Run (scale-to-zero) for the API +
  **Postgres, Redis, and the RQ worker on one Always-Free e2-micro VM** (via
  `docker-compose.dev.yml`) + GCS/Artifact Registry/Cloud Build free tiers.
  Caveat: e2-micro's 1 GB RAM is marginal for this ML-heavy image — an
  `e2-small` (~$13/mo) or a free managed Postgres/Redis (Neon / Upstash) is safer.

## Build the image (both paths)

```bash
cd moltrace_backend
gcloud artifacts repositories create moltrace --repository-format=docker --location=us-central1
gcloud builds submit --config cloudbuild.yaml --substitutions=_TAG="$(git rev-parse --short HEAD)"
export IMG=us-central1-docker.pkg.dev/$(gcloud config get-value project)/moltrace/backend
```

## Deploy the API to Cloud Run — free-tier tuned (scale-to-zero)

```bash
gcloud run deploy moltrace-backend --image "$IMG:latest" --region us-central1 \
  --min-instances 0 --max-instances 2 --cpu 1 --memory 2Gi --concurrency 80 \
  --set-env-vars APP_ENV=production,LOG_LEVEL=info,ALLOWED_ORIGINS=https://moltrace.co \
  --set-secrets DATABASE_URL=DATABASE_URL:latest,REDIS_URL=REDIS_URL:latest,API_KEY=API_KEY:latest,ADMIN_EMAILS=ADMIN_EMAILS:latest \
  --allow-unauthenticated --port 8080
```

- `--min-instances 0` is what keeps it in the free tier — the trade is a **cold
  start** on the first request after idle (torch/faiss/rdkit imports are heavy;
  `--memory 2Gi` helps). Set `--min-instances 1` only once you're past eval.
- Run migrations **once** before/after deploy — never in the container start
  command (every instance would race). As a Cloud Run Job:

```bash
gcloud run jobs create moltrace-migrate --image "$IMG:latest" --region us-central1 \
  --set-secrets DATABASE_URL=DATABASE_URL:latest --command alembic --args upgrade,head
gcloud run jobs execute moltrace-migrate --region us-central1 --wait
```

## Data + worker

- **Path A:** Cloud SQL + Memorystore over a Serverless VPC connector (main runbook,
  Phases 1–2), and the worker as a `--no-cpu-throttling` service or Cloud Run worker pool.
- **Path B:** `docker compose -f deploy/docker-compose.dev.yml up -d db redis worker`
  on the e2-micro VM; point the Cloud Run API's `DATABASE_URL`/`REDIS_URL` secrets
  at the VM's internal IP (same VPC), or run the whole compose stack locally for dev.

## Notes carried from the main runbook

- **Raw-FID vault + DVC** must target GCS on Cloud Run (ephemeral FS) — a small
  backend swap in `raw_vault.py` / `versioning.py`, not just config.
- **Secrets** load from Secret Manager as env vars, matching `settings.resolve_secret`.
- Keep the fail-closed CI release gate; only the deploy target changes (keyless via
  Workload Identity Federation — no stored SA key).

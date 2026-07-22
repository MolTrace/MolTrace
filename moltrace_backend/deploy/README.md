# MolTrace backend on GCP — verified deploy runbook

**Status: live.** This is not theory — every command below was run end-to-end against a
fresh project on 2026-07-22 and the result answers `{"status":"ok","checks":{"app":"ok","database":"ok"}}`.

Container + build files live one level up: [`Dockerfile`](../Dockerfile),
[`.dockerignore`](../.dockerignore), [`.gcloudignore`](../.gcloudignore),
[`cloudbuild.yaml`](../cloudbuild.yaml). Local stack: [`docker-compose.dev.yml`](docker-compose.dev.yml).

---

## ⚠️ Five gotchas that will bite you

These are the things that actually broke. Read them before running anything.

### 1. `alembic upgrade head` CANNOT bootstrap a fresh database

The Alembic chain is a set of **Postgres deltas that assume the ORM schema already
exists**. Migration `0007` references `dataset_versions`, a table no migration creates —
it comes from the ORM. Against an empty database you get
`UndefinedTable: relation "dataset_versions" does not exist`.

The schema is built by `init_db()` → `Base.metadata.create_all()` (260 tables), which the
app runs **at startup** (`api.py`). So for a **new** database:

```
deploy the app  ->  it creates the schema  ->  alembic stamp head
```

Use `alembic upgrade head` only for **subsequent** releases against a database that
already exists. Getting this backwards costs an hour.

### 2. Alembic's version column is too narrow for our revision ids

`alembic_version.version_num` is `VARCHAR(32)`, but seven revision ids are 34–38 chars
(e.g. `0005_week25_nmr2d_run_canonical_fields`). A from-base run dies at `0003` with
`StringDataRightTruncation`. Fixed in `alembic/env.py`, which now pre-creates/widens the
table to `VARCHAR(255)` before Alembic makes its own. Idempotent and safe on existing DBs.

### 3. `.dockerignore` / `.gcloudignore` do NOT inherit `.gitignore`

A git-ignored local venv (`torch_env/`, **626 MB**) was invisible to git but fully visible
to the build context: **16,256 files / 436 MiB uploaded per build**. After adding
`torch_env/` and `*_env/`: **640 files / 9.0 MiB**. If a build upload looks large, this is why.

### 4. Cloud SQL now defaults to Enterprise **Plus**, which rejects shared-core tiers

`--tier=db-f1-micro` fails with *"Invalid Tier (db-f1-micro) for (ENTERPRISE_PLUS) Edition"*.
You must pass **`--edition=ENTERPRISE`** for any `db-f1-micro` / `db-g1-small` instance.

### 5. Cloud Build's service account needs explicit IAM on new projects

Google stopped auto-granting the Compute Engine default SA broad rights, so the first
build fails with a 403 reading *its own uploaded source*. Grant
`storage.objectViewer`, `artifactregistry.writer`, `logging.logWriter`.

**Bonus:** Serverless VPC **connectors are billable** (~$8–15/mo). Use Cloud Run
**Direct VPC egress** (`--network` + `--subnet` + `--vpc-egress`) instead — same private
access to Cloud SQL, no connector instances to pay for.

---

## What "free tier" actually covers

GCP has **two** different "free" things:

| | What it is | Good for |
| --- | --- | --- |
| **$300 credit** | 90 days against any service | Trialling the real managed architecture |
| **Always Free** | Perpetual, capped, some services only | A $0/mo dev setup |

Cloud Run (scale-to-zero), Artifact Registry (0.5 GB), Cloud Build (120 min/day), GCS
(5 GB) and Secret Manager all have Always-Free tiers. **Cloud SQL and Memorystore do
not** — cheapest are ~$9/mo (`db-f1-micro`) and ~$35/mo (1 GB Redis).

**As deployed here: ~$9/mo total** (Cloud SQL only; Redis deferred, API scales to zero).

---

## The verified sequence

```bash
# ---- Phase 0: project ----
gcloud auth login
gcloud projects create moltrace-prod --name="MolTrace" --organization=<ORG_ID>
gcloud config set project moltrace-prod
gcloud billing projects link moltrace-prod --billing-account=<BILLING_ID>
gcloud services enable run.googleapis.com sqladmin.googleapis.com redis.googleapis.com \
  secretmanager.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  vpcaccess.googleapis.com servicenetworking.googleapis.com cloudkms.googleapis.com \
  storage.googleapis.com aiplatform.googleapis.com compute.googleapis.com orgpolicy.googleapis.com

# ---- Phase 1: private network (no connector needed) ----
gcloud compute networks create moltrace-vpc --subnet-mode=custom
gcloud compute networks subnets create moltrace-subnet \
  --network=moltrace-vpc --region=us-central1 --range=10.10.0.0/24
gcloud compute addresses create google-svcs --global \
  --purpose=VPC_PEERING --prefix-length=16 --network=moltrace-vpc
gcloud services vpc-peerings connect --service=servicenetworking.googleapis.com \
  --ranges=google-svcs --network=moltrace-vpc     # retry once if it errors; it races API enablement

# ---- Phase 2: data + secrets ----
gcloud sql instances create moltrace-db --database-version=POSTGRES_16 \
  --edition=ENTERPRISE --tier=db-f1-micro --region=us-central1 \
  --network=projects/moltrace-prod/global/networks/moltrace-vpc \
  --no-assign-ip --storage-auto-increase --availability-type=zonal
gcloud sql databases create moltrace --instance=moltrace-db
PW="$(openssl rand -base64 40 | tr -dc 'A-Za-z0-9' | head -c 40)"
gcloud sql users create moltrace --instance=moltrace-db --password="$PW"
IP="$(gcloud sql instances describe moltrace-db --format='value(ipAddresses[0].ipAddress)')"
printf 'postgresql+psycopg://moltrace:%s@%s:5432/moltrace' "$PW" "$IP" \
  | gcloud secrets create DATABASE_URL --data-file=-
# plus: API_KEY, ADMIN_EMAILS, AUDIT_SIGNING_KEY, SSO_ENCRYPTION_KEY,
#       MFA_ENCRYPTION_KEY, PASSWORD_PEPPER
gcloud storage buckets create gs://moltrace-raw-vault --location=us-central1 \
  --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://moltrace-raw-vault --versioning

# ---- Phase 3: IAM ----
gcloud iam service-accounts create moltrace-run
SA=moltrace-run@moltrace-prod.iam.gserviceaccount.com
for R in cloudsql.client secretmanager.secretAccessor storage.objectAdmin; do
  gcloud projects add-iam-policy-binding moltrace-prod \
    --member="serviceAccount:$SA" --role="roles/$R" --condition=None; done
# Cloud Build SA (see gotcha 5) — <PROJECT_NUMBER>-compute@developer.gserviceaccount.com
for R in storage.objectViewer artifactregistry.writer logging.logWriter; do
  gcloud projects add-iam-policy-binding moltrace-prod \
    --member="serviceAccount:<PROJECT_NUMBER>-compute@developer.gserviceaccount.com" \
    --role="roles/$R" --condition=None; done

# ---- Phase 4: build ----
gcloud artifacts repositories create moltrace --repository-format=docker --location=us-central1
cd moltrace_backend
gcloud builds submit --config cloudbuild.yaml --substitutions=_TAG="$(git rev-parse --short HEAD)"

# ---- Phase 5: deploy (schema is created on startup) ----
gcloud run deploy moltrace-backend \
  --image us-central1-docker.pkg.dev/moltrace-prod/moltrace/backend:latest \
  --region us-central1 --service-account "$SA" \
  --network moltrace-vpc --subnet moltrace-subnet --vpc-egress private-ranges-only \
  --set-env-vars APP_ENV=production,LOG_LEVEL=info,ALLOWED_ORIGINS=https://moltrace.co \
  --set-secrets DATABASE_URL=DATABASE_URL:latest,API_KEY=API_KEY:latest,ADMIN_EMAILS=ADMIN_EMAILS:latest,AUDIT_SIGNING_KEY=AUDIT_SIGNING_KEY:latest,SSO_ENCRYPTION_KEY=SSO_ENCRYPTION_KEY:latest,MFA_ENCRYPTION_KEY=MFA_ENCRYPTION_KEY:latest,PASSWORD_PEPPER=PASSWORD_PEPPER:latest \
  --cpu 2 --memory 2Gi --concurrency 80 --min-instances 0 --max-instances 2 \
  --timeout 300 --port 8080 --allow-unauthenticated

# ---- Phase 6: stamp Alembic (NEW db) — see gotcha 1 ----
gcloud run jobs create moltrace-migrate \
  --image us-central1-docker.pkg.dev/moltrace-prod/moltrace/backend:latest \
  --region us-central1 --service-account "$SA" \
  --network moltrace-vpc --subnet moltrace-subnet --vpc-egress private-ranges-only \
  --set-secrets DATABASE_URL=DATABASE_URL:latest \
  --command alembic --args stamp,head
gcloud run jobs execute moltrace-migrate --region us-central1 --wait
# For LATER releases against this same DB, switch the job to: --args upgrade,head
```

Verify: `curl https://<service-url>/health` → `{"status":"ok","checks":{"app":"ok","database":"ok"}}`

---

## Still outstanding

- **Raw-FID vault → GCS.** Cloud Run's filesystem is ephemeral, so `raw_vault.py` must
  target `gs://moltrace-raw-vault` before real uploads. `RawStorageBackend` already
  abstracts this and `S3RawStorageBackend` is a stub — implement a GCS backend against
  the same contract, plus a settings-driven factory (none exists; `api.py` hardcodes
  `local_raw_vault`). Same for the DVC remote in `versioning.py`.
- **RQ worker + Memorystore.** Deferred (~$35/mo). The worker doesn't serve HTTP, so on
  Cloud Run it needs a worker pool, a health-server wrapper, or a small VM.
- **Domain + CI/CD.** Map `api.moltrace.co`; deploy from GitHub Actions via Workload
  Identity Federation (keyless), keeping the existing fail-closed release gate.

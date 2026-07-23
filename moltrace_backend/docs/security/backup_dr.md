# Backup & Disaster-Recovery Resilience

**Security Prompt 21.** How MolTrace backs up data, what the recovery objectives are,
how a restore is **verified for integrity**, and how a region-loss restore is drilled.

> **Honest boundary.** On Google Cloud, the **backup retention/config, cross-region
> replication, retention-lock (WORM) policies, and *executing* a region-loss restore**
> are operational — they live in the Cloud console / `gcloud` against project
> `moltrace-prod` (region `us-central1`), not in this repo. What ships in-repo is the
> **restore-integrity verifier** ([`dr_verify.py`](../../src/nmrcheck/dr_verify.py)), the
> create-only vault write path, the RTO/RPO targets, and the drill / game-day runbooks
> below. Cross-region + retention-locked backups are a **seam**
> (see [Operational TODOs](#operational-todos)); do not read the targets below as a
> guarantee — they are the objectives the operational program is built to meet.

## What is backed up

| Asset | Mechanism | Owner |
|---|---|---|
| **Primary database** (`moltrace-db`, Cloud SQL for PostgreSQL 16 on a **private IP**, reached over Direct VPC egress) — all tenant data, the tamper-evident audit ledger, security events | Cloud SQL **automated backups** (daily, retained in-region) + **point-in-time recovery** from WAL archiving once PITR is enabled on the instance (see [Operational TODOs](#operational-todos)) | Google Cloud (platform) |
| **Raw-data vault** (write-once vendor archives) | **Cloud Storage** bucket `gs://moltrace-raw-vault` (`RAW_VAULT_BACKEND=gcs`) with Google's regional durability/replication; **object versioning on**, uniform bucket-level access + public-access prevention; writes are create-only (`if_generation_match=0`, never overwrite). **The local vault's `0o444` write-once chmod does *not* apply in production** — Cloud Run's filesystem is ephemeral, so immutability rests on the bucket's versioning / retention policy, not on file mode | Google Cloud (platform) + in-repo backend |
| **Secrets** (API key, audit signing key, IdP/MFA secrets) | not in backups — re-provisioned on restore from **Secret Manager** (injected into Cloud Run via `--set-secrets`); the field-encryption key comes from **Cloud KMS** | Operational |
| **Code + IaC + container image** | git (this repo, incl. `moltrace_backend/Dockerfile`) — the image is rebuilt via `gcloud builds submit` into Artifact Registry — plus the [signed supply chain](../supply_chain_provenance.md) | In-repo |

The database is the system of record; this doc focuses on its recovery, because the
audit ledger inside it is the integrity oracle for *every* restore.

## Recovery objectives (RTO / RPO)

| Tier | RPO (max data loss) | RTO (max downtime) |
|---|---|---|
| **Database (tenant data + audit ledger)** | ≤ 24 h (daily automated backup); ≤ 5 min with Cloud SQL point-in-time recovery enabled on the instance | ≤ 4 h to restore + integrity-verify + cut over |
| **Application (stateless web services)** | 0 (rebuilt from git + the verified supply chain) | ≤ 1 h (redeploy from `main`) |

These are **objectives**, not SLAs; they are validated by the restore drill below and
revised against measured drill results. A region-loss event recovers by restoring the
Cloud SQL backup/PITR point into an instance in a secondary region and redeploying the
stateless Cloud Run service there from the same Artifact Registry image.

## Restore-integrity verification — the in-repo half

A restore is not "done" until it is **proven intact**. The audit ledger is the natural
oracle: a restored DB whose per-row SHA-256 hash chain + HMAC anchors + signed
high-water mark still verify is *provable* evidence that nothing was lost or altered in
transit. After any restore, run:

```bash
# Point at the RESTORED database, then:
python -m nmrcheck.dr_verify --min-rows audit_events=1,users=1,security_events=1
```

`dr_verify` ([`src/nmrcheck/dr_verify.py`](../../src/nmrcheck/dr_verify.py)) checks:

1. **audit_chain** — the full chain + anchors + signed head re-verify (reuses Prompt 10's
   `verify_audit_chain`). A break ⇒ the restore lost or altered records.
2. **audit_history_present** — the restored DB actually contains chained audit events
   (catches an empty / wrong-database restore).
3. **signing_key_not_dev** — the restored deployment is using the **production**
   `AUDIT_SIGNING_KEY`, not the dev fallback (a dev key means the chain's tamper-evidence
   can't be trusted — re-provision the key before relying on the restore).
4. **row_counts_meet_baseline** — core tables meet the pre-loss baseline (a data-loss /
   wrong-snapshot guard; pass the baseline from the last good backup manifest via
   `--min-rows`).

Exit `0` = **integrity verified** (the "verified for integrity" half of the DR
acceptance criterion); `1` = a check failed; `2` = could not connect. The logic is
unit-tested (`tests/test_dr_verify.py`) against a seeded (clean) and a tampered DB.

## Restore drill procedure

Run on a schedule (quarterly) and after any major schema change:

1. **Pick a recovery point** (a recent automated backup / PITR timestamp).
2. **Capture the baseline** — record core-table row counts from the source (the
   `--min-rows` input).
3. **Restore** the backup into an **isolated, non-production** target (never overwrite
   prod) — operational, in the Cloud console / `gcloud sql` (`instances clone
   --point-in-time` or `backups restore` into a **new** instance, optionally in the
   secondary region).
4. **Integrity-verify** — run `dr_verify` against the restored DB (above). Record the
   pass/fail + the elapsed time (your measured RTO).
5. **Smoke** — bring up the app against the restored DB (a scratch Cloud Run revision or
   job whose `DATABASE_URL` points at the restored instance, on the same VPC); confirm
   `/health`, `GET /admin/audit/verify`, and a representative read.
6. **Record** — drill date, recovery point, measured RTO/RPO, `dr_verify` result, gaps →
   [findings register](security_findings_register.md) rows. Update the RTO/RPO targets if
   the drill missed them.

## DR game-day template

```
Date / facilitator:
Scenario: <e.g. primary region us-central1 (Cloud SQL moltrace-db) lost at HH:MM UTC>
Recovery point chosen (RPO): <backup/PITR timestamp>   →   data-loss window: <Δ>
Restore target: <isolated Cloud SQL instance / secondary region — NOT prod>
Timeline:
  T0  region-loss declared
  T+? restore initiated
  T+? restore complete
  T+? dr_verify run → <INTEGRITY VERIFIED | FAILED: which check>
  T+? app smoke green → cutover
Measured RTO: <T_cutover − T0>   vs target ≤ 4h
Gaps / surprises → findings-register rows:
Decision: did we meet RTO/RPO? what changes?
```

## <a id="operational-todos"></a>Operational TODOs (outside this repo)

- **Point-in-time recovery** — Cloud SQL automated backups are the baseline, but **PITR
  (WAL archiving) is a per-instance toggle** (`gcloud sql instances patch moltrace-db
  --enable-point-in-time-recovery`). Until it is on, the DB RPO is the daily-backup
  window (≤ 24 h), not the ≤ 5 min target above.
- **Cross-region + retention-locked backups** — `moltrace-db` is a **single-zone
  (`--availability-type=zonal`) instance with in-region backups**; add cross-region
  backup copies / a cross-region replica (and regional HA if the RTO tightens) so a
  region loss can't take the backups with it. On the vault side, `gs://moltrace-raw-vault`
  has **object versioning** but **no retention (bucket-lock) policy** — add one for
  durable WORM, plus a dual-region/turbo-replication or second-region copy. (The GCS
  backend already warns when a bucket has neither retention nor versioning.)
- **Encryption** — backups and objects are encrypted at rest by default with
  Google-managed keys; confirm whether CMEK (Cloud KMS) is required for the DB/bucket,
  and that the restore re-provisions secrets from Secret Manager / Cloud KMS, never from
  a backup.
- **Scheduled drills + game-days** — run the procedure above quarterly; automate the
  `dr_verify` step in the drill pipeline (a Cloud Run job against the restored instance
  is the natural harness).
- **Secrets recovery** — `AUDIT_SIGNING_KEY` and the field-crypto KEK must be recoverable
  independently of the DB backup (else a restored chain can't be verified / secrets
  decrypted) — they live in Secret Manager / Cloud KMS, and `dr_verify`'s
  `signing_key_not_dev` check surfaces a missing signing key.

## Cross-references

[`zero_trust_infra.md`](zero_trust_infra.md) (platform/shared-responsibility) ·
[`incident_response_plan.md`](incident_response_plan.md) (a data-loss event is an
incident) · [`security_findings_register.md`](security_findings_register.md) (drill
gaps) · the audit chain (`GET /admin/audit/verify`) is the same integrity primitive
`dr_verify` reuses.

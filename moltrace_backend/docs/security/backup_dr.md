# Backup & Disaster-Recovery Resilience

**Security Prompt 21.** How MolTrace backs up data, what the recovery objectives are,
how a restore is **verified for integrity**, and how a region-loss restore is drilled.

> **Honest boundary.** On a Render PaaS, the **backup storage, cross-region replication,
> immutable/object-lock retention, and *executing* a region-loss restore** are
> operational — they live in the Render console + a secondary region/account, not in
> this repo. What ships in-repo is the **restore-integrity verifier**
> ([`dr_verify.py`](../../src/nmrcheck/dr_verify.py)), the RTO/RPO targets, and the
> drill / game-day runbooks below. Cross-region + immutable backups are a **seam**
> (see [Operational TODOs](#operational-todos)); do not read the targets below as a
> guarantee — they are the objectives the operational program is built to meet.

## What is backed up

| Asset | Mechanism | Owner |
|---|---|---|
| **Primary database** (`moltrace-db`, managed Postgres) — all tenant data, the tamper-evident audit ledger, security events | Render automated backups (daily + point-in-time recovery on the paid tier) | Render (platform) |
| **Raw-data vault** (write-once vendor archives) | object storage with the platform's durability/replication | Platform |
| **Secrets** (API key, audit signing key, IdP/MFA secrets) | not in backups — re-provisioned from the secret store / KMS on restore (`generateValue` / env) | Operational |
| **Code + IaC** | git (this repo) + the [signed supply chain](../supply_chain_provenance.md) | In-repo |

The database is the system of record; this doc focuses on its recovery, because the
audit ledger inside it is the integrity oracle for *every* restore.

## Recovery objectives (RTO / RPO)

| Tier | RPO (max data loss) | RTO (max downtime) |
|---|---|---|
| **Database (tenant data + audit ledger)** | ≤ 24 h (daily backup); ≤ 5 min with point-in-time recovery on the paid tier | ≤ 4 h to restore + integrity-verify + cut over |
| **Application (stateless web services)** | 0 (rebuilt from git + the verified supply chain) | ≤ 1 h (redeploy from `main`) |

These are **objectives**, not SLAs; they are validated by the restore drill below and
revised against measured drill results. A region-loss event recovers by restoring the
DB into a secondary region and redeploying the stateless app there.

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
   prod) — operational, in the Render console / secondary region.
4. **Integrity-verify** — run `dr_verify` against the restored DB (above). Record the
   pass/fail + the elapsed time (your measured RTO).
5. **Smoke** — bring up the app against the restored DB; confirm `/health`,
   `GET /admin/audit/verify`, and a representative read.
6. **Record** — drill date, recovery point, measured RTO/RPO, `dr_verify` result, gaps →
   [findings register](security_findings_register.md) rows. Update the RTO/RPO targets if
   the drill missed them.

## DR game-day template

```
Date / facilitator:
Scenario: <e.g. primary region (Render Postgres) lost at HH:MM UTC>
Recovery point chosen (RPO): <backup/PITR timestamp>   →   data-loss window: <Δ>
Restore target: <isolated region/instance — NOT prod>
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

- **Cross-region + immutable backups** — replicate the automated backups to a second
  region and to object-lock (WORM) storage so a region loss or a malicious/buggy delete
  can't take the backups with it. (Render's in-region automated backups are the baseline;
  cross-region/immutable is the hardening seam.)
- **Encryption** — confirm backups are encrypted at rest (platform default) and that the
  restore re-provisions secrets from the KMS/secret store, never from a backup.
- **Scheduled drills + game-days** — run the procedure above quarterly; automate the
  `dr_verify` step in the drill pipeline.
- **Secrets recovery** — `AUDIT_SIGNING_KEY` and the field-crypto KEK must be recoverable
  independently of the DB backup (else a restored chain can't be verified / secrets
  decrypted) — `dr_verify`'s `signing_key_not_dev` check surfaces a missing signing key.

## Cross-references

[`zero_trust_infra.md`](zero_trust_infra.md) (platform/shared-responsibility) ·
[`incident_response_plan.md`](incident_response_plan.md) (a data-loss event is an
incident) · [`security_findings_register.md`](security_findings_register.md) (drill
gaps) · the audit chain (`GET /admin/audit/verify`) is the same integrity primitive
`dr_verify` reuses.

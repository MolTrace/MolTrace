# CSPM — IaC posture scoring + drift detection (Security Prompt 18)

A lightweight **Cloud Security Posture Management** layer for MolTrace's declarative
infrastructure. It turns the existing Trivy `config` (IaC) scan into a
**continuously-scored, drift-alerting** gate: the committed baseline records the
*accepted* set of HIGH/CRITICAL misconfigurations, and CI **fails on any new
misconfiguration not in that baseline** — so posture drift is caught the moment it
lands, not only when it escalates to CRITICAL.

This is the in-repo slice of zero-trust infrastructure. The broader controls
(private networking, cloud IAM, CIS host hardening, runtime protection,
auto-remediation) are platform/operational and are documented honestly in
[`../../moltrace_backend/docs/security/zero_trust_infra.md`](../../moltrace_backend/docs/security/zero_trust_infra.md).

## Files

- **`score_iac_posture.py`** — pure-stdlib scorer. Reads a `trivy config --format json`
  report, extracts the FAILing HIGH/CRITICAL misconfigurations (`id::target::severity`), diffs
  against the baseline, and exits non-zero on drift. `--update` re-baselines.
- **`iac_posture_baseline.json`** — the accepted-posture baseline (the "score").
  `accepted` is currently empty: the gated IaC tree (`render.yaml` blueprints + the
  GitHub Actions workflows) has **zero** HIGH/CRITICAL misconfigurations.

## What scans, what's scored

The `iac` job in `.github/workflows/security-scan.yml` runs `trivy config` over the
declarative infra (it skips `node_modules` / `.next`, so vendored Dockerfiles in
dependencies are not scored). Trivy's own gate still hard-blocks **CRITICAL**; this
drift gate additionally blocks any **new HIGH/CRITICAL** relative to the baseline.

## Updating the baseline (a deliberate, reviewed act)

When a misconfiguration is genuinely accepted (a compensating control or an
unavoidable platform constraint), re-baseline and record *why* in the baseline's
`notes` map — mirroring the `.trivyignore` VEX register for dependencies:

```bash
trivy config --format json --severity HIGH,CRITICAL \
  --skip-dirs '**/node_modules' --skip-dirs 'moltrace_frontend/.next' \
  -o trivy-iac.json .
python3 infra/cspm/score_iac_posture.py \
  --trivy-json trivy-iac.json \
  --baseline infra/cspm/iac_posture_baseline.json --update
# then edit iac_posture_baseline.json `notes` to justify each accepted entry, and commit.
```

The scorer's logic is unit-tested in
`moltrace_backend/tests/test_cspm_drift.py` (no Trivy needed — synthetic reports).

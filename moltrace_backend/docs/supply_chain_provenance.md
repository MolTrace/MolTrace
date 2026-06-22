# SBOM, provenance & signing (Security Prompt 15)

MolTrace emits a **CycloneDX SBOM per build**, attaches **SLSA build provenance** signed **keylessly
via Sigstore**, and **gates deploy on provenance verification** so nothing reaches the deploy hooks
unsigned. All of this lives in `.github/workflows/ci-cd.yml` (jobs `sbom-backend`, `sbom-frontend`,
`attest`, `verify-provenance`) so it is part of the same gated pipeline as the test + deployment
gates.

## What is produced, per build

| Artifact | Source | Tool | Spec |
|---|---|---|---|
| `sbom-backend.cdx.json` | `moltrace_backend/uv.lock` | `uv export --format cyclonedx1.5` | CycloneDX 1.5 |
| `sbom-frontend.cdx.json` | `moltrace_frontend/pnpm-lock.yaml` | `pnpm sbom --sbom-format cyclonedx` (pnpm ≥ 11, built-in) | CycloneDX 1.7 |
| SLSA provenance (`slsa.dev/provenance/v1`) | both SBOMs | `actions/attest-build-provenance@v4` | in-toto DSSE, Sigstore-signed |

The SBOMs upload as workflow artifacts each run. The provenance attestation is **keyless**: the
`attest` job's OIDC token (`id-token: write`) is exchanged with Sigstore/Fulcio for a short-lived
signing certificate, the in-toto statement is signed, the key is discarded, and the attestation is
persisted to the repository's attestation store (`attestations: write`). No key is stored or managed.

## Verify-at-deploy — "nothing deploys unsigned"

`ci-cd.yml`'s `deploy` job `needs: [frontend-tests, backend-tests, deployment-gate,
verify-provenance]`. The `verify-provenance` job downloads the **exact** attested SBOM artifacts
(same run — digests match by construction, no nondeterministic regeneration) and runs:

```
# In CI the workflow templates ``--repo "$REPO"`` off ``${{ github.repository }}`` so it self-
# adjusts on any future transfer/rename. The shape from the operator's shell, where
# ``<owner>`` is whichever account holds MolTrace at the time you check (originally
# ``sirmcdoe``; on transfer to a GitHub org for the attestations API, that org's slug):
gh attestation verify sbom-artifacts/<sbom> \
  --repo <owner>/MolTrace \
  --signer-workflow <owner>/MolTrace/.github/workflows/ci-cd.yml
```

for each SBOM. Any verification failure fails the job, and because `deploy` *needs* it, **none** of
the Vercel / Render deploy hooks fire. It is a **separate gating job** (not an in-`deploy` step) on
purpose: the deploy hook steps use `if: always()` (so a Vercel hiccup can't block Render), which a
failed in-job step would not stop — only an unmet `needs:` stops them all.

> A `serialNumber`/`timestamp` makes each CycloneDX document non-byte-stable across runs, so the
> gate verifies the *same-run attested file*, never a regenerated one (regenerate-then-verify-by-
> digest would false-block).

## Provenance queryable per release

Every push-to-`main` mints an attestation keyed to the SBOM digests, queryable on demand:

```
gh attestation verify <sbom-file> --repo <owner>/MolTrace
gh api /repos/<owner>/MolTrace/attestations/sha256:<digest>
```

The `verify-provenance` run log prints the verified subject digests, so each release's provenance is
auditable from the deploy run and re-checkable later.

## Honest limitations (deploy-hook boundary)

- **The platforms rebuild from source.** Vercel and Render rebuild from the git ref *after* the
  deploy hook fires — outside CI's signing boundary. The attestation therefore covers the
  **source + dependency closure (SBOM) at the gated commit**, not the artifact the platforms serve.
  This is a real, defensible supply-chain control for a hook-based deploy; it is not container-image
  signing (there is no CI-built image to sign).
- **The gate is only effective with platform auto-deploy disabled.** Vercel auto-deploy is
  file-disabled (`moltrace_frontend/vercel.json` `git.deploymentEnabled: false`) and both Render
  services have Auto-Deploy = No, so the gated CI `deploy` job is the only trigger path. Anyone with
  a deploy-hook URL or dashboard access could still deploy out-of-band — operational access control,
  not a CI control.
- **uv's CycloneDX exporter is PREVIEW** (v1.5 only; "may change in any future release"). The two
  SBOMs differ in spec version (BE 1.5 / FE 1.7) and tool — acceptable, each is lockfile-native and
  accurate for its ecosystem. Revisit when uv's exporter stabilises.
- **Private-repo Sigstore:** keyless attestations on a private/internal repo use GitHub's own
  Sigstore instance (no public Rekor) and require GitHub Enterprise Cloud for that path; on a public
  repo the Public-Good Rekor transparency log is used.
- **The attestations API is gated by GitHub's repo-ownership policy.** ``actions/attest-build-
  provenance`` calls ``POST /repos/{owner}/{repo}/attestations`` to persist the SLSA bundle, and
  GitHub blocks that endpoint on **user-owned private repositories** ("Feature not available for
  user-owned private repositories"). The endpoint is available on public repos and on repos owned
  by a **GitHub Organization** (any visibility). The fix is one of: transfer MolTrace to a GitHub
  org (free; the workflow templates ``${{ github.repository }}`` so no edit is needed) or make the
  repo public. Until either lands, the ``attest`` job will fail, ``verify-provenance`` will be
  skipped via its ``needs:`` link, and ``deploy`` will be skipped too — the deploy gate is
  honestly fail-closed under this constraint.

These controls **support** a customer's secure-SDLC / SLSA posture; they do not by themselves certify
the deployed artifact end-to-end.

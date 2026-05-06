# Week 24.4: Immutable Raw FID Vault

This module makes the uploaded raw NMR archive the source of truth. Preview,
processing, review, and export all operate from a verified immutable archive and
write only derivative records.

## Architecture Diagram Text

```text
User upload (.zip/.tar.gz/.tgz)
  -> safe archive inspection
  -> SHA-256 digest
  -> RawStorageBackend
       -> LocalRawStorageBackend: raw_data_vault/{sha256}/{filename}
       -> S3RawStorageBackend: placeholder for production object storage
  -> raw_archives database row
  -> preview/process request
       -> hash verification
       -> temporary extraction / in-memory arrays
       -> FFT / phase / baseline / peak picking
       -> FIDProcessingRun + evidence metadata
  -> export package
       -> verified original archive + analysis metadata + manifest hashes
```

## Raw Archive Lifecycle

1. Upload accepts a raw vendor archive and immediately computes SHA-256.
2. Archive members are inspected without trusting paths or extracting into the
   vault.
3. Supported acquisition metadata is parsed from Bruker `acqus`/optional
   `procs`/`pulseprogram` or Varian/Agilent `procpar`.
4. The untouched archive is stored by content hash.
5. The local development vault sets the stored file read-only where supported.
6. A `raw_archives` row records filename, byte size, SHA-256, storage path,
   vendor, dataset root, files found, acquisition metadata, and warnings.
7. Preview, processing, download, and export recalculate SHA-256 before use.
8. Processing creates derivative run metadata and never writes back to the raw
   archive or extracted vendor folder.

## Supported Formats

- Bruker 1D archive: `.zip`, `.tar.gz`, or `.tgz`, with `fid` or future `ser`
  plus `acqus`.
- Varian/Agilent 1D archive: `.zip`, `.tar.gz`, or `.tgz`, usually a `.fid`
  folder with `fid` and `procpar`.

Unsafe archive entries are rejected: absolute paths, `..` traversal, symlinks,
hardlinks, devices, special files, excessive expanded size, and excessive file
count.

## SHA-256 Integrity Model

The archive digest is generated from the exact uploaded bytes. The stored object
is verified on write and again before preview, process, download, or export.

If verification fails, the API blocks the operation, writes
`raw_fid.integrity_failure`, and returns:

```text
Raw archive hash mismatch. Processing blocked to protect data integrity.
```

The public utility is `verify_raw_archive_integrity(...)`, which returns a report
with expected/actual SHA-256, expected/actual byte size, existence, warning, and
`ok`.

## Non-Destructive Processing Policy

Raw archives and raw vendor binaries are never edited. Processing does this:

```text
verified raw archive
  -> temporary extraction
  -> copied in-memory FID arrays
  -> Fourier transform / phase correction / baseline correction
  -> derived spectrum preview and peak list
  -> FIDProcessingRun metadata
```

Processing outputs are evidence artifacts, not replacements for the original
FID.

## Processing Recipe Model

Each raw FID processing run stores a structured `FIDProcessingRecipe` including:

- vendor and nucleus
- processing preset
- digital-filter correction status
- apodization mode and line broadening
- zero-fill factor and Fourier transform status
- phase mode, p0, p1, and score
- baseline correction mode and order
- reference ppm and solvent
- peak sensitivity and solvent masking
- display mode, vertical gain, and debug-preview flag

Safe defaults are `phase_mode=auto`, `baseline_correction=bernstein`,
`baseline_order=3`, `display_mode=real`, `vertical_gain=1.0`, and
`debug_preview=false`.

## Export Package Structure

`GET /raw-fid/{archive_id}/export` returns a zip package:

```text
manifest.json
raw/
  original_archive.zip or original_archive.tar.gz
analysis/
  analysis.json
  processing_recipe.json
  acquisition_metadata.json
  peak_list.csv
  spectrum_preview.json
  evidence_report.json
  audit_trail.json
```

`manifest.json` contains SHA-256 hashes for the original archive,
`processing_recipe.json`, `analysis.json`, `peak_list.csv`, and
`evidence_report.json`.

## Local Dev Setup

Environment settings:

```text
RAW_VAULT_DIR=raw_data_vault
RAW_ARCHIVE_MAX_BYTES=2147483648
RAW_ARCHIVE_MAX_FILES=5000
RAW_ARCHIVE_ALLOWED_EXTENSIONS=.zip,.tar.gz,.tgz
RAW_ARCHIVE_IMMUTABLE=true
RAW_ARCHIVE_REQUIRE_HASH_VERIFICATION=true
```

`RAW_DATA_VAULT_DIR` remains accepted as a backward-compatible alias for older
deployments, but `RAW_VAULT_DIR` is the current setting name.

## Storage Backends

`src/nmrcheck/raw_vault.py` defines:

- `RawStorageBackend`
- `LocalRawStorageBackend`
- `S3RawStorageBackend`

`LocalRawStorageBackend` is the active implementation for development. It stores
archives at `raw_data_vault/{sha256}/{filename}` and verifies hashes before
reads.

`S3RawStorageBackend` is intentionally a placeholder. A production
implementation should use S3 Object Lock or equivalent immutability, versioning,
server-side encryption, conditional writes, IAM least privilege, lifecycle
rules, and checksum verification before reads.

## Endpoints

- `POST /raw-fid/upload`
- `GET /raw-fid/{archive_id}`
- `GET /raw-fid/{archive_id}/download`
- `POST /raw-fid/{archive_id}/preview`
- `POST /raw-fid/{archive_id}/process`
- `GET /raw-fid/{archive_id}/runs`
- `GET /raw-fid/{archive_id}/export`

Legacy `/fid/preview` and `/fid/process` remain for compatibility, but the UI
uses the explicit immutable-vault workflow.

## UI Policy

The Raw FID panel communicates:

- Original raw FID archive is never modified.
- Processing creates derived evidence only.
- Display gain does not alter evidence data.

There is no "save raw" or overwrite action.

## Limitations

- The local vault is suitable for development and single-machine testing, not
  regulated production retention by itself.
- S3/object storage is designed but not fully implemented.
- 2D `ser` support is detected for future use, but this module focuses on 1D raw
  FID preview and processing.
- Vendor metadata extraction is conservative and reads common fields only.
- Human review remains required for raw FID-derived interpretation.

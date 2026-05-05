# Week 37 — LC-MS Feature Grouping + Blank Subtraction + Retention-Time Alignment

This module groups detected LC-MS features across multiple runs and prepares a cleaner, auditable feature table for downstream HRMS, MS/MS, unified confidence, and report workflows.

## Scope

The module accepts open/processed LC-MS sources through the existing Week 36 feature-detection layer. It supports sample, blank, QC, and reference run roles.

It provides:

- conservative retention-time shift alignment using shared feature anchors;
- feature grouping by m/z and aligned retention time;
- blank/background area subtraction;
- blank-like and possible-background flags;
- isotope, adduct, and in-source-loss mass-difference hints;
- run-level SHA-256 provenance;
- exportable grouped feature table text.

## Endpoints

```text
POST /ms/lcms/features/group
POST /ms/lcms/features/group/evidence
POST /ms/lcms/features/group/upload
```

## Important limitations

Retention-time alignment is a simple shift correction, not full chromatographic warping. Blank subtraction is evidence triage, not proof of identity. Feature-family annotations are mass-difference hints and must be reviewed by a human before structural claims are made.

## Stable-state protection

This package must not alter NMR, FID, HRMS, adduct inference, processed MS/MS, fragmentation-tree, unified confidence, report composer, LC-MS import, or Week 36 feature-detection contracts.

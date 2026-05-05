# Week 30: Processed MS/MS Annotation Beta

## Purpose

Week 30 adds the second mass-spectrometry layer. Week 29 constrained candidates using HRMS exact mass; Week 30 adds processed tandem-MS evidence:

```text
NMR evidence + predicted NMR matching + HRMS exact mass + processed MS/MS fragments
```

The goal is a practical beta layer for centroid peak tables, not full raw LC-MS/MS handling.

## New Module

```text
src/nmrcheck/msms.py
```

## New Endpoints

```text
POST /ms/msms/annotate
POST /ms/msms/annotate/evidence
```

## New UI Section

```text
Processed MS/MS Annotation Beta
```

It appears in the Analysis tab after `HRMS / Exact-Mass Constraint Layer` and before `Processed spectrum upload`.

## Supported Input

Processed centroid peak tables:

```text
m/z,intensity
47.04914,10
29.03913,100
```

CSV, whitespace, and tab-separated rows are accepted.

## What the Beta Annotates

- precursor/adduct exact-mass consistency
- common neutral losses
- candidate-specific simple single-bond fragments
- fragment m/z matching under absolute Da and ppm tolerances
- explained peak count
- explained relative-intensity fraction
- candidate support labels

## Supported Adduct Reuse

The layer reuses the Week 29 HRMS adduct system:

```text
[M+H]+
[M+Na]+
[M+K]+
[M+NH4]+
[M-H]-
[M+Cl]-
[M+FA-H]-
[M+Ac-H]-
M
```

## Neutral-Loss Examples

The transparent rule set includes:

```text
H2O
NH3
CO
C2H4
CH3OH
H2S
HCl
C2H2O
CO2
CH3COOH
SO2
HBr
```

Candidate structures are used to mark whether a neutral loss is chemically plausible. For example, H2O is more plausible with oxygen/hydroxyl/carboxyl features, while HCl and HBr require chlorine or bromine support.

## Why This Layer Comes Before Raw LC-MS/MS

Raw LC-MS/MS support requires data-format, chromatographic, vendor-library, mzML, metadata, peak-picking, and deconvolution work. A processed peak-table beta gives immediate scientific value while preserving the NMR stack.

## Limitations

This is not yet a full fragmentation-tree engine. It does not yet:

- parse raw Thermo/Waters/Agilent/Bruker LC-MS files;
- perform chromatographic peak picking;
- infer precursor/adduct automatically from a full run;
- model collision energy;
- search GNPS/MassBank/HMDB/MoNA;
- generate exhaustive fragmentation trees;
- create de novo molecular hypotheses.

## Human Review Rule

MS/MS annotations are evidence, not a verdict. Fragments and neutral losses support or weaken a proposed structure but do not prove complete connectivity or stereochemistry. Human review remains required.

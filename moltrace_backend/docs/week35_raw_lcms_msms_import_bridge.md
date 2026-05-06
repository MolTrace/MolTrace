# Week 35: Raw LC-MS/MS mzML + Processed Peak Import Bridge

## Purpose

Week 35 starts moving SpectraCheck from processed MS peak tables toward real LC-MS/MS workflows while preserving the stable NMR/MS stack.

The bridge accepts:

- mzML text / files
- mzXML text / files
- processed LC-MS/MS peak tables
- unsupported vendor-file placeholders, with clear conversion warnings

It returns:

- raw/source SHA-256 provenance hash
- immutable raw-data flag
- MS1 scan summaries
- MS2 scan summaries
- TIC/base-peak chromatogram summary
- extracted MS1 peak list for adduct/isotope inference
- selected MS/MS peak list for MS/MS annotation and fragmentation-tree reasoning
- precursor inventory
- warnings, limitations, and next actions

## New module

```text
src/nmrcheck/lcms_import.py
```

## New endpoints

```text
POST /ms/lcms/import/bridge
POST /ms/lcms/import/bridge/evidence
POST /ms/lcms/import/bridge/upload
```

## New UI section

```text
Raw LC-MS/MS mzML + Processed Peak Import Bridge
```

Placement:

```text
Regulatory-ready Structure Elucidation Report Composer
↓
Raw LC-MS/MS mzML + Processed Peak Import Bridge
↓
Processed spectrum upload
```

## What this layer deliberately does not do

This package does not add full vendor raw parsing, database search, mzML transformation pipelines, MS-Numpress decoding, chromatographic deconvolution, library matching, or generative unknown-compound proposals.

It is a safe import bridge that turns portable open-format or processed MS data into downstream SpectraCheck inputs.

## Supported input styles

### Processed peak table

```text
scan_id,ms_level,rt_min,mz,intensity,precursor_mz
ms1_001,1,0.50,47.04914,100,
ms1_001,1,0.50,48.05249,2.3,
ms2_001,2,0.51,29.03858,100,47.04914
```

### mzML

The bridge reads conservative mzML metadata and decodes common uncompressed/zlib 32-bit or 64-bit floating-point m/z and intensity arrays. MS-Numpress arrays are not decoded in this lightweight layer.

### mzXML

The bridge reads scan metadata and decodes common interleaved m/z/intensity peak arrays.

### Vendor raw files

Vendor-specific files are not parsed. The bridge returns a clear warning to convert them to mzML/mzXML or export processed peak tables while preserving the original raw file and hash.

## Literature-driven design takeaways

- LC/GC/MS desktop workflows commonly include TIC navigation, scan selection, peak detection, molecule match, elemental composition, MS prediction, and MS tables; this package implements the first SpectraCheck-native bridge into that workflow.
- Accurate mass, isotope evidence, molecular formula, DBE/IHD, and MS/MS daughter-ion interpretation are core small-molecule structure-elucidation tools, so imported MS1/MS2 peak lists should feed HRMS, isotope/adduct, MS/MS, and fragmentation-tree modules.
- Computational MS literature emphasizes the difficulty of proprietary raw data access, metadata complexity, vendor library limitations, and the need for open/interoperable formats; the package therefore supports mzML/mzXML and warns on vendor-specific files.
- Defensive programming requires bounded parsing, explicit warnings, immutable raw-data handling, provenance hashes, and regression tests.

## Tests

```text
tests/test_week35_lcms_import_bridge.py
tests/test_week35_lcms_ui.py
tests/test_week35_lcms_api.py
```

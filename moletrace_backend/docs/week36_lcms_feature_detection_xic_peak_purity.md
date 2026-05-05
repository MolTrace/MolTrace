# Week 36: LC-MS Feature Detection + EIC/XIC + Peak Purity

## Purpose

Week 36 turns the Week 35 LC-MS/MS import bridge into an analysis layer that can detect chromatographic features from MS1 scans.

The goal is to support this workflow:

```text
mzML/mzXML or processed LC-MS peak table
→ MS1 scan series
→ EIC/XIC extraction for target m/z values
→ chromatographic feature detection
→ local peak-purity estimate
→ nearby MS/MS precursor links
→ HRMS / MS/MS / unified confidence / report handoff
```

## New module

```text
src/nmrcheck/lcms_features.py
```

## New endpoints

```text
POST /ms/lcms/features/detect
POST /ms/lcms/features/detect/evidence
POST /ms/lcms/features/detect/upload
```

## New UI section

```text
LC-MS Feature Detection + EIC/XIC + Peak Purity
```

It appears in the Analysis tab after `Raw LC-MS/MS mzML + Processed Peak Import Bridge` and before `Processed spectrum upload`.

## Supported inputs

The feature layer accepts the same source styles as the import bridge:

- processed LC-MS peak tables with columns such as `scan_id`, `ms_level`, `rt_min`, `mz`, `intensity`, and `precursor_mz`;
- mzML text/files with conservatively decoded MS1/MS2 arrays;
- mzXML text/files with conservatively decoded peak pairs.

Vendor raw files are not parsed directly. They should be converted to mzML/mzXML or exported as processed peak tables while preserving the original raw-file SHA-256.

## Main outputs

Each result includes:

- source format;
- SHA-256 provenance hash;
- scan counts;
- TIC/base-peak chromatogram summary;
- extracted XIC points;
- detected features;
- apex retention time;
- integrated area;
- feature width;
- signal-to-noise estimate;
- peak-purity report;
- top coeluting ions;
- linked MS/MS precursor scans;
- warnings and recommended next actions.

## Feature labels

```text
clean_feature
possible_coelution
weak_or_no_feature
invalid_input
```

## Peak-purity labels

```text
high_purity
possible_coelution
poor_peak_purity
not_assessed
```

## Scientific limitations

Peak purity is chromatographic evidence, not structural proof. Coeluting ions may be isotope peaks, adducts, in-source fragments, background ions, or true impurities. The feature layer should therefore support human review and downstream candidate scoring rather than replace expert interpretation.

## Why this comes after Week 35

Week 35 created a non-destructive import bridge from LC-MS/MS files or processed peak tables into downstream MS evidence modules. Week 36 adds the next required chromatographic layer: determining whether a candidate m/z has a real chromatographic peak, whether it is clean enough to trust, and whether nearby MS/MS scans plausibly belong to that same feature.

## Downstream handoff

The best feature can be copied to:

- HRMS observed m/z;
- unified confidence HRMS m/z;
- MS/MS precursor m/z;
- fragmentation-tree precursor m/z;
- structure report processing history.

The report composer should record the source SHA-256 and the feature detection settings.

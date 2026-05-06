
# Week 22: ¹³C NMR Validation Layer

## Purpose

¹³C NMR is the bridge between the existing ¹H NMR workflow and future HSQC/HMBC/COSY logic.

The core workflow is:

```text
SMILES -> expected carbon count
¹³C NMR text/table -> observed carbon signals
solvent heuristics -> remove likely solvent carbon peaks
region heuristics -> classify carbon environments
report -> interpretation + confidence
```

## Supported input

### Text

```text
¹³C NMR (101 MHz, CDCl3) δ 58.3, 18.2.
```

### CSV/TSV

Required chemical-shift column can be one of:

```text
shift_ppm
ppm
shift
delta
```

Optional columns:

```text
intensity
height
area
assignment
label
```

### JSON

```json
[
  {"shift_ppm": 58.3, "assignment": "CH2"},
  {"shift_ppm": 18.2, "assignment": "CH3"}
]
```

or

```json
{"peaks": [{"shift_ppm": 58.3}]}
```

## Endpoints

```text
POST /carbon13/validate
POST /carbon13/analyze
POST /carbon13/upload
```

## Limitations

This is a validation heuristic, not a full ¹³C assignment engine. Missing peaks can be caused by overlap, symmetry, weak quaternary carbons, relaxation issues, or low signal-to-noise.

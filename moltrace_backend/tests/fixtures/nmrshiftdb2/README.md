# NMRShiftDB2 Raw FID Fixtures

Small representative raw FID fixtures downloaded from NMRShiftDB2 for
`read_fid` regression tests.

Source index:

- `source/nmrshiftdb2rawdata.nmredata.sd`
- SHA-256: `d38b64581ed3d8495a11855215358a33eebfebe4492be46c7144ede71d36f807`

Downloaded paired Bruker raw-data archives for NMRShiftDB2 `DB_ID=75667`:

- `raw/nmrshiftdb2_75667_1h.zip`
  - Spectrum ID: `40255417`
  - SHA-256: `81ca60adc0f585fb78293e3f162f1a07f32bd6abe81e0a8f32d4319ea1d1afbf`
  - Extracted copy: `raw/extracted/nmrshiftdb2_75667_1h_bruker/`
- `raw/nmrshiftdb2_75667_13c.zip`
  - Spectrum ID: `40255414`
  - SHA-256: `fdf02ef03dafc73ad1521b1d0ca62366d4a85557810e1cfc3a03ba77a77e9fa0`
  - Extracted copy: `raw/extracted/nmrshiftdb2_75667_13c_bruker/`

The expected JSON files intentionally store both NMReDATA curated solvent
metadata and Bruker `acqus` solvent metadata when they differ.

The broader Prompt 1 validation set is described by:

- `expected/nmrshiftdb2_bruker_20.json`
  - 20 Bruker 1D raw-data archives prepared from the local NMReDATA source index
  - each fixture records its archive SHA-256, extracted Bruker dataset path,
    processed reference peak positions, and acceptance tolerances

Refresh the 20-FID set with:

```bash
cd moltrace_backend
python3 scripts/prepare_nmrshiftdb2_bruker_fixtures.py --limit 20
```

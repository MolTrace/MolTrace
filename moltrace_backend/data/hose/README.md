# HOSE-code knowledge base (deployment slot)

Drop a **precomputed index** here as `hose_index.json.gz` before building the
image and it is baked in; `MOLTRACE_HOSE_KB` already points at it.

```bash
python scripts/build_hose_kb.py <nmrshiftdb2.nmredata.sd> --index \
    -o data/hose/hose_index.json.gz
```

Get the source export (271 MB) from
<https://sourceforge.net/projects/nmrshiftdb2/files/data/nmrshiftdb2.nmredata.sd/download>.

## Why the index and not the raw table

| form | size | load |
|---|---|---|
| molecules + assignments | 193 MB | ~47 s (re-parses 49,618 molblocks with RDKit) |
| **precomputed index (gz)** | **14 MB** | **~1 s** (no RDKit) |

A 47 s cold start is incompatible with a scale-to-zero service. The index makes
the table shippable at all — which is why the cheap path beats a GPU here.

## If this directory is empty

The predictor falls back to the bundled 16-molecule seed table. That is a
**working but poor** state: on drug-like molecules ~23-44% of atoms resolve to a
bare element prior and the median ¹³C uncertainty is ~35 ppm, versus 1.88 ppm
with the full table. It is reported honestly at runtime — every prediction
carries `prior_fallback_fraction` and `median_uncertainty_ppm`, and a coverage
warning — so this degrades visibly rather than silently. It is not a state to
deploy to production on purpose.

## Licensing

The built table is a NMRShiftDB2 derivative under **CC BY-SA**; ShareAlike
attaches on redistribution, including inside a shared container image. See
`NOTICE`. Contents of this directory are gitignored — never commit the table.

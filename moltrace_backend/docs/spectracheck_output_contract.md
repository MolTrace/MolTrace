# SpectraCheck Output Contract (downstream integration)

**Status:** stable · **Schema version:** `1.0.0` · **Source of truth:**
`moltrace.spectroscopy.infra.contract`

SpectraCheck is the **first** MolTrace module (Roadmap Phase 2 alpha) and the
upstream source of truth for the downstream modules:

- **Regulatory Intelligence Hub** — consumes confirmed structures + impurity /
  purity calls.
- **ReactionIQ** — consumes analytical verification in the closed optimisation
  loop.

So that those modules can depend on SpectraCheck **without breaking when the
pipeline internals change**, every analysis serialises to a *stable, versioned,
content-addressed* output contract. Downstream code should depend on **this
contract**, never on the pipeline's internal Python objects.

---

## The envelope

`SpectraCheckContract.to_envelope()` returns the wire form:

```json
{
  "schema_version": "1.0.0",
  "content_hash": "sha256:<hex>",
  "contract": { ...contract body... }
}
```

- **`schema_version`** — the contract schema version (see *Versioning* below).
- **`content_hash`** — `sha256:<hex>` over the canonical JSON of the contract
  body. The same analysis input always produces the same hash (the determinism
  kernel the end-to-end CI smoke test pins), so the hash is a stable identity for
  caching, deduplication, and audit-trail cross-reference.
- **`contract`** — the analysis body (below).

`to_canonical_json()` returns the canonical JSON of the whole envelope (sorted
keys, fixed float precision, NaN/Inf rejected) — byte-reproducible across runs and
platforms.

## The contract body (`to_dict()`)

| Key | Shape | Meaning |
|---|---|---|
| `schema_version` | `"1.0.0"` | embedded for self-describing payloads |
| `contract_id` | `"moltrace.spectracheck.contract"` | stable contract identifier |
| `spectrum` | `{nucleus, solvent, field_mhz, ppm_range:[lo,hi], n_points}` | acquisition context |
| `peaks` | sorted list of `{ppm, intensity, area, width_hz, category, confidence}` | detected peaks (order-independent) |
| `multiplets` | sorted list of `{name, center_ppm, range_ppm, multiplicity, j_couplings_hz, num_nuclides}` | multiplet analysis |
| `classification_summary` | `{category: count}` | peak-category histogram (compound / solvent / impurity / …) |
| `integration` | object | integration / proton-count result |
| `provenance` | `{fingerprint_hash, pipeline_version, schema_version}` | reproduction lineage |

Lists are stored **already sorted** (peaks by ppm, multiplets by centre), so two
runs that detect the same features produce an identical contract — and therefore
an identical `content_hash` — independent of detection order.

## Building a contract

```python
from moltrace.spectroscopy.infra.contract import (
    build_spectracheck_contract,   # from primitive peak/multiplet dicts
    contract_from_pipeline,        # from live pipeline objects (duck-typed)
    SCHEMA_VERSION,
)

contract = build_spectracheck_contract(
    nucleus="1H", solvent="CDCl3", field_mhz=400.0,
    ppm_range=(0.0, 12.0), n_points=16384,
    peaks=[{"ppm": 7.26, "category": "solvent"}],
)
envelope = contract.to_envelope()          # schema_version + content_hash + contract
```

Only the standard library + numpy are imported, so the contract layer is usable
and testable in complete isolation from the rest of the pipeline.

---

## Versioning & stability policy

`SCHEMA_VERSION` follows semantic versioning of the **contract shape** (not the
pipeline's `version`):

- **Patch / minor (`1.0.x` / `1.x.0`)** — *additive, backward-compatible* changes:
  a new optional key, a new peak category value, a new provenance field.
  Downstream consumers that ignore unknown keys keep working unchanged.
- **Major (`2.0.0`)** — a *backward-incompatible* shape change: renaming or
  removing a key, changing a value type, restructuring a section. Bumped only when
  unavoidable, announced in the backend `CHANGELOG.md`, and paired with a
  downstream migration note.

**Consumer guidance:** pin to a **major** version, read keys defensively (tolerate
new optional keys), and assert `schema_version` starts with the major you support.
Use `content_hash` as the analysis identity for cross-module references.

## Release gating

This contract is part of the Prompt 18 release controls. The deployment gate
(`moltrace.spectroscopy.ops.deployment_gate`) fails closed unless every check
passes, and the end-to-end determinism CI gate proves the same input serialises to
a byte-identical contract on every run — so a downstream module can trust that a
given `content_hash` always means the same analysis.

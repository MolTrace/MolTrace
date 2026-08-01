# Backend handoff — structure & reaction scheme service

**For:** a backend session. Do not start this from a frontend session.
**Frontend state:** shipped and working (`f00ce18`, `fe4d670`). It draws, imports and
captures entirely in-browser. It calls **no endpoint**, and it says so on screen.
**Blocking:** attaching a captured scheme to a project, and any claim that a
structure has been checked.

---

## 1. Why this is backend-first

Per the repo's contracts-first rule, the FastAPI routes and models land **before**
the frontend consumes them, and `schema.d.ts` is regenerated in between. The
frontend deliberately stops at "captured in this browser only" rather than
inventing a contract from this side.

There is also a correctness reason. Ketcher's in-browser Indigo engine is a
*drawing* engine. It will happily hand back a structure that RDKit — the engine
every other MolTrace chemistry decision already runs on (qNMR purity,
verification scoring, NMR prediction, MS models, Q3C solvents, M7 classifier) —
would read differently or reject. Two engines disagreeing silently is exactly the
failure a regulated workspace cannot absorb. **RDKit is the authority; Ketcher is
the pencil.**

---

## 2. What the frontend will send

Captured by `StructureEditorPanel` today, typed in
`moltrace_frontend/src/components/chemistry/StructureEditor.tsx`:

```ts
type StructureSnapshot = {
  block: string            // MDL molfile OR MDL RXN block — lossless
  format: "mol" | "rxn"    // which one `block` is
  smiles: string           // Daylight SMILES; MAY BE EMPTY (see below)
}
```

Three things to design around, all observed rather than assumed:

1. **`format` is load-bearing.** An RXN block is not a molfile. Ketcher's
   `getMolfile()` throws outright on anything with a reaction arrow
   (`"The structure cannot be saved as *.MOL due to reaction arrows"`). Parse with
   `Chem.MolFromMolBlock` vs `AllChem.ReactionFromRxnBlock` on this field — do not
   sniff the string.
2. **`smiles` can be empty and that is not an error.** SMILES generation fails on
   valid-but-exotic drawings (query atoms, R-groups) — precisely the drawings a
   SMARTS query is made of. Treat `block` as the source of truth and `smiles` as a
   convenience.
3. **Sizes are small but unbounded.** A pasted SDF can be large. Cap the request
   body and reject early with a plain-language message.

---

## 2b. What already exists — check before building

**A single structure already has a home, and it already gets canonicalized.**
`POST /compound-registry/compounds/{compound_id}/structures` accepts a drawn
structure today, and the frontend now uses it (`a9…`, this session). Verified
against the running service:

```
→ { structure_input: "<molfile>", structure_format: "mol", source: "user_entered",
    validation_status: "not_checked", reviewer_status: "unreviewed", metadata_json: {…} }
← 201 { id, canonical_smiles, inchi, inchikey, formula, exact_mass,
        normalization_warnings_json: [...], validation_status, reviewer_status }
```

RDKit runs on the way in, and the response carries the verdict — for a drawn
aspirin it returned `formula: "C9H8O4"` and a canonical SMILES. So **do not
rebuild single-structure canonicalization**; §3 below is now only needed for
(a) checking *before* committing a record, and (b) reactions, which this
endpoint cannot hold.

Three enum traps, each of which produced a 422 during integration — the values
are literals, not free text:

| field | allowed |
|---|---|
| `structure_format` | `smiles` `mol` `sdf` `inchi` `name_only` `unknown` — **no `rxn`** |
| `source` | `user_entered` `spectracheck_candidate` `reaction_product` `regulatory_dossier` `imported_sdf` `report` `other` |
| `validation_status` | `valid` `invalid` `ambiguous` `not_checked` |
| `reviewer_status` | `unreviewed` `accepted` `rejected` `needs_changes` |

The absence of `rxn` from `structure_format` is the registry stating that a
reaction is not a compound structure. Respect that rather than widening the enum
— reactions want §4.

---

## 3. Endpoint 1 — validate & canonicalize (reactions, and pre-commit checks)

```
POST /reactions/structures/validate
```

**Request**

```json
{ "block": "<molfile or RXN>", "format": "mol" | "rxn", "smiles": "optional" }
```

**Response** (`200` — a structure that fails chemistry checks is still a *successful*
request; the verdict is in the body, not the status code)

```json
{
  "ok": true,
  "format": "rxn",
  "canonical_smiles": "CC(Cl)=O.OCC>>CC(OCC)=O",
  "normalized_block": "<RDKit-round-tripped block>",
  "inchikey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
  "atom_count": 13,
  "bond_count": 13,
  "component_counts": { "reactants": 2, "agents": 0, "products": 1 },
  "warnings": [
    { "code": "unusual_valence", "message": "Nitrogen at atom 4 has 4 bonds and no charge.", "atom_indices": [4] }
  ],
  "errors": []
}
```

- `ok: false` with a populated `errors[]` when RDKit cannot parse it at all.
- **`warnings` must be plain language.** No RDKit exception text, no
  `MolFromMolBlock`, no status codes — this string goes straight onto a chemist's
  screen. See `feedback_no_backend_jargon_in_user_copy`.
- `inchikey` only when a single, fully-defined structure — omit for reactions and
  for anything with query atoms, rather than emitting a misleading key.

**Do NOT sanitize silently.** If RDKit's sanitization changes the structure
(kekulization, aromaticity perception, implicit-H changes), say so in `warnings`.
A chemist who draws one thing and gets another stored without being told is the
worst outcome here.

---

## 4. Endpoint 2 — attach to a project

```
POST /reaction-projects/{reaction_project_id}/schemes
```

Persist the **normalized** block plus the captured original. Both, not one: the
original is what the chemist drew and is the audit record; the normalized form is
what downstream code should compute on.

Suggested columns: `reaction_project_id`, `format`, `source_block`,
`normalized_block`, `canonical_smiles`, `inchikey`, `created_by_user_id`,
`created_at`, `warnings_json`.

Owner-scoping and the ALCOA+ soft-delete pattern apply, same as dossiers — see
`project_dossier_access_control` and `reference_alcoa_controlled_records_fe`.
`GET` and `PATCH`/soft-delete to match.

---

## 5. Endpoint 3 — SMARTS query (optional, second slice)

```
POST /reactions/structures/smarts-match
{ "smarts": "...", "targets": ["<smiles>", ...] }
```

Compile with `Chem.MolFromSmarts` and reuse **the same code path as the R6
structural safety screen** (`project_repho_safety_screening_fe`). Two SMARTS
engines in one product will drift, and the screen is the one with a review gate
already built around it.

---

## 6. Frontend checklist once the contract exists

1. `cd moltrace_frontend && npm run generate:openapi` — regenerate
   `src/lib/api/schema.d.ts`. Do not hand-write the types.
2. `StructureEditorPanel` gains an "Attach to project" action next to "Capture
   scheme", enabled only once a snapshot exists.
3. Replace the standing line *"Captured in this browser only. Chemistry checks and
   attaching it to the project need the reaction service, which this build does not
   yet call."* with the real verdict — canonical SMILES, atom/bond counts, and any
   warnings, rendered as plain text.
4. Warnings render as an `AlertCard variant="warning"`; a failed parse as
   `variant="error"`. Never block the user from re-editing the canvas.
5. **Send the body the server declares.** Several MolTrace models are
   `extra="forbid"`, and an extra key produces a 100%-reproducible 422. Diagnose by
   A/B-posting to a nonexistent id: 422 = wrong shape, 404 = right shape. See
   `reference_fe_extra_forbid_422_class`.

---

## 7. Deliberately out of scope

- **Structure search across the registry.** Substructure/similarity search over
  stored structures is a much larger piece (fingerprints, an index, a query
  planner) and should not be smuggled in behind "validate".
- **Server-side depiction.** The browser already renders; a PNG/SVG render
  endpoint is only needed once schemes appear in exported reports.
- **Atom-atom mapping.** Ketcher can express it and RDKit can read it, but nothing
  downstream consumes it yet. Store it if present in the block; do not build a
  mapper.

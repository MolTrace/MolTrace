# Frontend handoff — the structure & reaction scheme contract now exists

**Answers:** `MolTrace_Structure_Editor_BE_Handoff.md` (§2b amendment included).
**Backend state:** built, tested, committed. Routes are live in `create_app()`.
**What changes for you:** `StructureEditorPanel` can stop saying "captured in this browser
only" and show a real verdict.

---

## 1. Do this first

```bash
cd moltrace_frontend && npm run generate:openapi
```

That rewrites `src/lib/api/schema.d.ts` from the live `/openapi.json`. Do not hand-write the
types — the generated schema is the binding contract.

## 2. Contract delta, by name

New schema components:

| name | role |
|---|---|
| `StructureValidateRequest` / `StructureValidateResponse` | check a drawing |
| `StructureIssue` | one warning or error (`code`, `message`, `atom_indices`) |
| `StructureComponentCounts` | `reactants` / `agents` / `products` |
| `ReactionStructureSchemeCreate` / `ReactionStructureScheme` | attach + read a scheme |
| `ReactionStructureSchemeDeleteRequest` | `reason_for_change`, required |
| `StructureSmartsMatchRequest` / `StructureSmartsMatchResponse` / `StructureSmartsMatchResult` | SMARTS query |

New routes:

| method | path |
|---|---|
| `POST` | `/reactions/structures/validate` |
| `POST` | `/reactions/structures/smarts-match` |
| `POST` | `/reaction-projects/{reaction_project_id}/schemes` → `201` |
| `GET` | `/reaction-projects/{reaction_project_id}/schemes?include_deleted=false` |
| `GET` | `/reaction-projects/{reaction_project_id}/schemes/{scheme_id}` |
| `POST` | `/reaction-projects/{reaction_project_id}/schemes/{scheme_id}/archive` |

## 3. Shapes

**Validate** — send exactly the `StructureSnapshot` you already capture:

```jsonc
// POST /reactions/structures/validate
{ "block": "<molfile or RXN>", "format": "mol", "smiles": "" }   // smiles may be ""
```

```jsonc
// 200 — ALWAYS 200 when the request is well-formed, even if the structure is unsound
{
  "ok": true,
  "format": "mol",
  "canonical_smiles": "CC(=O)Oc1ccccc1C(=O)O",
  "normalized_block": "<RDKit molfile>",
  "inchikey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",   // null for reactions and R-group drawings
  "atom_count": 13,
  "bond_count": 13,
  "component_counts": null,                     // populated only when format is "rxn"
  "warnings": [ { "code": "…", "message": "…", "atom_indices": [4] } ],
  "errors": [],
  "validator_version": "reaction_structures.v1"
}
```

**Read `ok`, not the status code.** A structure that fails its chemistry checks is a
*successful* request with `ok: false` and a populated `errors[]`. Only a malformed request
(bad shape, oversized block) is a 4xx.

For a **reaction**, `canonical_smiles` is order-normalized — components are sorted within each
role, so `A.B>>C` and `B.A>>C` produce the same string and it is safe to use as an identity or
dedup key. `normalized_block` keeps the drawn component order, so a scheme still renders the way
the chemist laid it out. Do not expect the two to list components in the same order.

**Attach** — `ReactionStructureSchemeCreate` is `StructureValidateRequest` plus `name` and
`metadata_json`:

```jsonc
// POST /reaction-projects/12/schemes
{ "block": "…", "format": "rxn", "smiles": "", "name": "Step 3 esterification",
  "metadata_json": {} }
```

Returns the stored `ReactionStructureScheme`, which carries **both** `source_block` (what was
drawn — the audit record) and `normalized_block` (what downstream chemistry uses), plus the
`warnings` as shown at capture time.

A drawing RDKit cannot read is **refused with `400`**, not stored — attaching it would let the
rest of the product treat an unchecked structure as checked. The message on that 400 is already
plain language; render it as-is.

**Archive** — `POST …/schemes/{id}/archive` with `{ "reason_for_change": "…" }`. A blank reason
is `422`. Archived schemes are retained, excluded from the default list, and returned by
`GET …/schemes?include_deleted=true`.

## 4. Message codes

Every `message` is already chemist-facing plain language — render it verbatim, do not rewrite
it. Use `code` only for icon/severity choice.

- *Warnings:* `hydrogen_count_changed`, `charge_changed`, `unpaired_electrons`,
  `atom_list_changed`, `aromatic_rings_written_out`, `explicit_hydrogens_folded_in`,
  `query_atoms_present`, `stereochemistry_undefined`, `drawn_smiles_differs`,
  `drawn_smiles_not_readable`
- *Errors:* `impossible_valence`, `ring_not_readable`, `structure_not_readable`,
  `empty_drawing`, `too_large`, `unsupported_format`, `checks_unavailable`

`atom_indices` are 0-based positions in the drawing's atom list, in block order, for
highlighting. For a **reaction** they are positions *within* the component the message names
("In reactant 2, …"), not across the whole scheme.

Two codes are worth surfacing prominently, because they are the reason this service exists:
`drawn_smiles_differs` (the editor's own SMILES disagrees with the drawing it came from) and
`hydrogen_count_changed` (what is stored is not what was drawn).

## 5. Watch for

- **`extra="forbid"`.** Every model above rejects unknown keys with a 100%-reproducible 422.
  Send `block` / `format` / `smiles` and nothing else on validate. Diagnose by A/B-posting to a
  nonexistent id: 422 = wrong shape, 404 = right shape.
- **`smiles: ""` is valid**, and is the expected value for query/R-group drawings.
- **Owner scoping.** The `…/schemes` routes are gated like the rest of Repho: a project you do
  not own returns `404 {"detail": "Not found."}`, identical to a missing project. Do not
  special-case it as an auth error.
- **Body cap** is 1,000,000 characters on `block`; over that is a 422 with a plain message.
- **`/reactions/structures/*` is licensed as a platform route, not as Repho.** Any module may
  call it — including a Regentry-only deployment, which needs it for the impurity round-trip
  before an ICH M7 verdict. Filed under Repho it returned `403 module_not_licensed` there.
  `…/schemes` is the opposite: it stays Repho-licensed, because a scheme belongs to a campaign.
  The `/reactions/` spelling is a misnomer kept for compatibility now that the panel calls it;
  see §8 if it is ever renamed.

## 8. If the validate path is ever renamed

`/reactions/structures/*` reads as a Repho route but is a shared chemistry primitive. Renaming
it to `/structures/*` needs backend and frontend to land together, because the panel already
calls the current path in three places:

- `src/lib/chemistry/structure-validation.ts` (the `apiFetch` call)
- `src/lib/chemistry/structure-validation.test.ts` and
  `src/components/chemistry/StructureEditorPanel.test.tsx` (both assert the path literal)
- plus `npm run generate:openapi` to refresh `schema.d.ts`

Not worth doing on its own; worth folding into the next change that touches this file.

## 6. Verify

```bash
cd moltrace_backend && .venv/bin/python -m pytest tests/test_reaction_structures.py -q
```

32 tests, all green, covering the engine, the registry cross-check, and every route above.

## 7. Still deliberately out of scope

Registry-wide substructure/similarity search, server-side depiction, and atom-atom mapping —
unchanged from your §7. Atom maps present in a block are stored, not interpreted.

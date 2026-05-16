/**
 * Shared compound-class taxonomy for SpectraCheck.
 *
 * The user picks a compound class once on the workspace "NMR text & candidate
 * structures" tab; every analyze/preview request that fans out to a backend
 * route forwards the canonical `value` as the `compound_class` parameter.
 *
 * Used by:
 *   - the Sample identity card selector in spectracheck-workspace.tsx
 *   - the processed 1H/13C spectrum section (FormData + job parameters)
 *   - the raw FID section (FormData + job parameters)
 *   - the MS evidence studio (job parameters)
 *
 * Keep the `value` strings stable — the backend matches against them via
 * `compound_class_value(...)` to validate and to bias candidate scoring.
 */

export const COMPOUND_CLASS_UNSPECIFIED = "unspecified" as const

export type CompoundClassValue =
  | "alkaloids"
  | "carbohydrates"
  | "fatty_acids"
  | "flavonoids"
  | "glycoproteins"
  | "lipids"
  | "macrocycles"
  | "macromolecules"
  | "natural_products"
  | "new_scaffolds"
  | "nucleic_acids"
  | "organometallics"
  | "peptides"
  | "polymers"
  | "proteins"
  | "small_molecules"
  | "steroids"
  | "terpenoids"
  | typeof COMPOUND_CLASS_UNSPECIFIED

export type CompoundClassOption = {
  value: CompoundClassValue
  label: string
  description: string
}

// Sorted alphabetically by user-visible ``label`` (case-insensitive).
// "Unspecified" lands at the bottom under strict alpha — it is still the
// default value (see workspace useState), only its position in the dropdown
// is alphabetised.
export const COMPOUND_CLASS_OPTIONS: readonly CompoundClassOption[] = [
  {
    value: "alkaloids",
    label: "Alkaloids",
    description: "Nitrogen-containing natural products of plant or microbial origin.",
  },
  {
    value: "carbohydrates",
    label: "Carbohydrates",
    description: "Mono-, oligo-, and polysaccharides, including glycans.",
  },
  {
    value: "fatty_acids",
    label: "Fatty acids",
    description: "Saturated and unsaturated long-chain carboxylic acids.",
  },
  {
    value: "flavonoids",
    label: "Flavonoids / polyphenols",
    description: "Plant polyphenolics: flavones, flavanones, isoflavones, anthocyanins.",
  },
  {
    value: "glycoproteins",
    label: "Glycoproteins",
    description: "Protein–carbohydrate conjugates and glycoconjugates.",
  },
  {
    value: "lipids",
    label: "Lipids",
    description: "Glycerolipids, glycerophospholipids, sphingolipids, sterol lipids.",
  },
  {
    value: "macrocycles",
    label: "Macrocycles",
    description: "Large ring systems including macrolides, cyclic peptides, and crown ethers.",
  },
  {
    value: "macromolecules",
    label: "Macromolecules",
    description: "Synthetic high-MW species: dendrimers, oligomers, biomolecule conjugates.",
  },
  {
    value: "natural_products",
    label: "Natural products",
    description: "Secondary metabolites from plants, microbes, or marine sources.",
  },
  {
    value: "new_scaffolds",
    label: "New scaffolds",
    description: "Novel chemotypes or exploratory structures with no fixed prior.",
  },
  {
    value: "nucleic_acids",
    label: "Nucleic acids",
    description: "DNA / RNA, nucleosides, nucleotides, oligonucleotides.",
  },
  {
    value: "organometallics",
    label: "Organometallics",
    description: "Compounds with one or more metal–carbon bonds.",
  },
  {
    value: "peptides",
    label: "Peptides",
    description: "Short amino-acid chains, typically < 50 residues.",
  },
  {
    value: "polymers",
    label: "Polymers",
    description: "Synthetic repeat-unit chains, copolymers, and block polymers.",
  },
  {
    value: "proteins",
    label: "Proteins",
    description: "Full-length folded proteins and large peptides.",
  },
  {
    value: "small_molecules",
    label: "Small molecules",
    description: "Typical drug-like organics, MW ≲ 900 Da.",
  },
  {
    value: "steroids",
    label: "Steroids",
    description: "Cyclopenta[a]phenanthrene-core skeletons and analogues.",
  },
  {
    value: "terpenoids",
    label: "Terpenoids",
    description: "Isoprenoid-derived natural products (mono-, sesqui-, di-, tri-, tetraterpenoids).",
  },
  {
    value: COMPOUND_CLASS_UNSPECIFIED,
    label: "Unspecified",
    description: "No class hint — analyzers run with default priors.",
  },
] as const

const VALUE_SET = new Set<string>(COMPOUND_CLASS_OPTIONS.map((opt) => opt.value))

/** Returns the canonical value when ``value`` is a known compound class, else null. */
export function normalizeCompoundClass(value: string | null | undefined): CompoundClassValue | null {
  if (!value) return null
  const trimmed = value.trim().toLowerCase()
  return VALUE_SET.has(trimmed) ? (trimmed as CompoundClassValue) : null
}

/**
 * Returns the compound class value to send to the backend, or null when the
 * caller should omit the parameter entirely (i.e. the user kept the default
 * "Unspecified" selection). Centralising this keeps the FormData / job
 * payload sites consistent — no half-sent "unspecified" strings.
 */
export function compoundClassForRequest(value: CompoundClassValue): string | null {
  if (value === COMPOUND_CLASS_UNSPECIFIED) return null
  return value
}

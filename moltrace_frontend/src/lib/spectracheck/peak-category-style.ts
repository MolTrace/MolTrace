/**
 * Peak-category palette shared between SpectrumViewer (Plotly hex values) and
 * the evidence panels (CSS-variable values). The two consumers need the same
 * grouping rules so a peak that reads "Aromatic" in the table renders in
 * the same hue on the chart.
 *
 * Categories are the public set returned by ``backend/peak_categorization.PEAK_CATEGORIES``.
 * If a future category is added there, append it here too with a sensible hue.
 */

export const PEAK_CATEGORY_PLOT_COLOR: Record<string, string> = {
  // Aromatic stays teal; OLEFINIC (only assigned when the SMILES actually has
  // C=C bonds) keeps the teal hue because both are sp2.
  aromatic_alkene: "#00B884",
  olefinic: "#00B884",
  // Aldehyde / carbonyl / carboxylic-acid OH / labile share amber.
  aldehyde: "#E8A030",
  carbonyl: "#E8A030",
  carboxylic_acid: "#E8A030",
  labile_OH_NH_SH: "#E8A030",
  // Heteroatom-adjacent CH + anomeric sugar protons all share slate-blue.
  // Anomeric is now its own category in the 4.4–6 ppm window when the SMILES
  // resolves to a carbohydrate-style sp3-C-with-two-O motif.
  oxygenated: "#4C6FAE",
  nitrogen_adjacent: "#4C6FAE",
  anomeric: "#4C6FAE",
  // Anomeric-OR-olefinic (ambiguous, no SMILES or both motifs present): use a
  // distinct purple so reviewers see immediately the categoriser couldn't
  // disambiguate. Click the legend entry to inspect.
  anomeric_or_olefinic: "#9333EA",
  // Aliphatic stays green to match the panel.
  aliphatic: "#22C55E",
  // Solvent / unknown stay muted so they don't dominate the chart.
  solvent: "#94A3B8",
  unknown: "#94A3B8",
  // Impurity is red — flags the eye.
  impurity: "#E84040",
}

export const PEAK_CATEGORY_DEFAULT_COLOR = "#EA580C"

export function plotColorForCategory(category: string | null | undefined): string {
  if (!category) return PEAK_CATEGORY_DEFAULT_COLOR
  return PEAK_CATEGORY_PLOT_COLOR[category] ?? PEAK_CATEGORY_DEFAULT_COLOR
}

/** Display name for a peak category. Matches ``humanizeCategory`` in the
 * evidence-panels file so legends + tables agree. ``anomeric_or_olefinic``
 * gets a hand-written label since the underscore-join "Anomeric or olefinic"
 * is grammatically awkward.
 */
export function humanizePeakCategory(category: string | null | undefined): string {
  if (!category) return "Peaks"
  if (category === "anomeric_or_olefinic") return "Anomeric / olefinic (ambiguous)"
  return category
    .replace(/_/g, " ")
    .replace("OH NH SH", "OH / NH / SH")
    .replace(/^\w/, (c) => c.toUpperCase())
}

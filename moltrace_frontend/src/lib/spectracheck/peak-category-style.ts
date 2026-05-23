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
  // Use distinct hues per category so mixed carbohydrate / impurity /
  // heteroatom regions remain visually separable in the legend.
  aromatic_alkene: "#00A6A6",
  olefinic: "#0EA5E9",
  aldehyde: "#D97706",
  carbonyl: "#7C2D12",
  carboxylic_acid: "#F59E0B",
  labile_OH_NH_SH: "#A16207",
  oxygenated: "#2563EB",
  nitrogen_adjacent: "#0F766E",
  anomeric: "#8B5CF6",
  carbohydrate_sugar: "#16A34A",
  // Anomeric-OR-olefinic (ambiguous, no SMILES or both motifs present): use a
  // distinct purple so reviewers see immediately the categoriser couldn't
  // disambiguate. Click the legend entry to inspect.
  anomeric_or_olefinic: "#9333EA",
  aliphatic: "#65A30D",
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
  if (category === "carbohydrate_sugar") return "Carbohydrate sugar backbone"
  return category
    .replace(/_/g, " ")
    .replace("OH NH SH", "OH / NH / SH")
    .replace(/^\w/, (c) => c.toUpperCase())
}

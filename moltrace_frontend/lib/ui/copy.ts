/**
 * Copy that is genuinely the SAME STRING in more than one place.
 *
 * The bar for living here is deliberately high: the phrase must be one
 * self-contained unit that should be reworded everywhere at once. A recurring
 * *phrase* used in different grammatical positions does not qualify — see the
 * note at the bottom.
 *
 * See `docs/ui_copy_style.md` for how the copy itself is written.
 */

/**
 * Heading for the raw-record disclosure that sits at the bottom of most
 * workspaces (usually behind developer mode). Used at 13 sites as a section
 * title, an `<h2>` and a `<summary>` — it reads as one recognizable affordance,
 * so it must not drift between them.
 */
export const RAW_DATA_DISCLOSURE = "Raw data (for troubleshooting)"

/**
 * Shown under a plot whose series was decimated for a small viewport, so a
 * reader does not mistake a simplified trace for the real resolution.
 */
export const PLOT_DOWNSAMPLED_NOTE =
  "Display downsampled on mobile. Full resolution available on desktop."

/** Tooltip on the plot-download control, shared by every scientific viewer. */
export const PLOT_DOWNLOAD_PNG_HINT = "Download the current plot as a PNG image."

/**
 * Deliberately NOT here: "Human review required".
 *
 * It occurs 33 times across 21 files, which looks like duplication and is not.
 * It appears as an alert title, a badge, a label preceding a value
 * ("Human review required: {flag}"), the opening of a full sentence
 * ("Human review required — a qualified chemist reviews every recommendation"),
 * and a qualified variant ("Human review required · local session"). One
 * constant cannot serve those positions; substituting it would yield
 * `{HUMAN_REVIEW_REQUIRED}: {flag}` — more indirection with no consistency
 * gained, since the surrounding words differ anyway.
 *
 * It is a standard phrase used correctly in many places, not copy that drifted.
 * Leave it inline.
 */

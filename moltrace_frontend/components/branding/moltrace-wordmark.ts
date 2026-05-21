import type { CSSProperties } from "react"

/** Styling for the “Trace” segment of MolTrace using the logo honeycomb cyan. */
export const moltraceTraceClassName =
  "font-extrabold tracking-tight text-[#26C6FF] opacity-100 antialiased"

/**
 * Flat treatment for the “MolTrace” wordmark. Keep this shared export so
 * existing header/footer call sites can opt into a consistent brand style
 * without adding the dark extruded shadow/reflection behind the text.
 */
export const moltraceWordmark3DStyle: CSSProperties = {}

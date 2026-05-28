import type { CSSProperties } from "react"

/**
 * Styling for the “Trace” segment of MolTrace.
 *
 * Two cyan variants because the bright honeycomb sky-cyan (#26C6FF) — the
 * same accent used inside the hex mark — fails WCAG AA on a white page
 * (contrast 1.7:1). We use the deeper teal-cyan #0E7490 (Tailwind cyan-700,
 * contrast 5.4:1 on white) in light mode and switch to the bright sky-cyan
 * in dark mode where the page background can carry it. ``next-themes``
 * toggles the ``dark`` class on ``<html>``, which Tailwind's ``dark:``
 * variant hooks into automatically.
 */
export const moltraceTraceClassName =
  "font-extrabold tracking-tight text-[#0E7490] dark:text-[#26C6FF] opacity-100 antialiased"

/**
 * Flat treatment for the “MolTrace” wordmark. Keep this shared export so
 * existing header/footer call sites can opt into a consistent brand style
 * without adding the dark extruded shadow/reflection behind the text.
 */
export const moltraceWordmark3DStyle: CSSProperties = {}

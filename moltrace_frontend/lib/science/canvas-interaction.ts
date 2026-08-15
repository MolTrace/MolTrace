/**
 * The MolTrace canvas gesture contract — one grammar for every spectrum canvas.
 *
 * ┌──────────────┬────────────────────────────────────────────────────────────────────┐
 * │ hover        │ crosshair + δ readout, no click needed                             │
 * │ drag         │ pan the visible window (mouse/pen; touch panning stays behind an   │
 * │              │ explicit move affordance so page scrolling keeps working)          │
 * │ shift+drag   │ zoom to the dragged window — the explicit chord, never the default │
 * │ wheel        │ vertical intensity, only while the canvas has keyboard focus       │
 * │ ← / →        │ pan 10% of the window in the arrow's SCREEN direction              │
 * │ + / −        │ zoom in / out about the window centre                              │
 * │ 0            │ full range and intensity ×1                                        │
 * │ double-click │ full range and intensity ×1                                        │
 * │ Esc          │ cancel the in-progress gesture / close the canvas menu.            │
 * │              │ NEVER resets the view — losing a zoom to a reflexive Esc is data   │
 * │              │ the reviewer had on screen and now has to find again.              │
 * │ right-click  │ canvas context menu, where the surface provides one                │
 * └──────────────┴────────────────────────────────────────────────────────────────────┘
 *
 * Two viewers implement this (SpectrumViewer, SpectrumStackViewer) and each previously had its own
 * answers: the stack zoomed on plain drag while the single viewer panned only in a toolbar mode,
 * and ArrowLeft panned the stack the wrong way. Same key, different outcome, is the failure this
 * module exists to end — so the maths lives here, and the viewers only dispatch.
 *
 * Everything here is pure. Wheel-focus gating, pointer capture, and Plotly/SVG plumbing stay in
 * the viewers: the anti-flicker architecture (static Plotly, RAF-coalesced updates) is theirs and
 * this module must never grow a dependency on it.
 */

export type CanvasSpan = { min: number; max: number }

/** Zoom-in factor for one `+` press — halves the window. Shared so both canvases step alike. */
export const CANVAS_ZOOM_IN_FACTOR = 0.5
/** Zoom-out factor for one `−` press — doubles the window. */
export const CANVAS_ZOOM_OUT_FACTOR = 2
/** Fraction of the visible window one arrow press pans by. */
export const CANVAS_PAN_FRACTION = 0.1
/** Bounds for the wheel-driven intensity multiplier. */
export const CANVAS_INTENSITY_MIN = 0.25
export const CANVAS_INTENSITY_MAX = 20

/**
 * Slide a window fully inside the domain without shrinking it; a window wider than the domain
 * becomes the domain. Sliding (not clipping) is what keeps a pan from silently zooming.
 */
export function clampSpanToDomain(span: CanvasSpan, domain: CanvasSpan): CanvasSpan {
  const width = span.max - span.min
  if (!Number.isFinite(width) || width <= 0) return { ...domain }
  if (width >= domain.max - domain.min) return { ...domain }
  if (span.min < domain.min) return { min: domain.min, max: domain.min + width }
  if (span.max > domain.max) return { min: domain.max - width, max: domain.max }
  return span
}

/**
 * Pan by one arrow press, in SCREEN terms.
 *
 * `screenDirection` −1 means "the view moves left". Chemical-shift axes are drawn reversed (high
 * ppm on the left), so view-left means HIGHER ppm there — the sign flip lives here precisely
 * because getting it wrong is invisible in code review and obvious at the bench. Returns null
 * when the window already covers the domain, so callers can no-op instead of jittering.
 */
export function panSpan(
  visible: CanvasSpan,
  domain: CanvasSpan,
  screenDirection: -1 | 1,
  options: { reversedX?: boolean; fraction?: number } = {},
): CanvasSpan | null {
  const { reversedX = true, fraction = CANVAS_PAN_FRACTION } = options
  const width = visible.max - visible.min
  if (width >= domain.max - domain.min) return null
  const delta = screenDirection * fraction * width * (reversedX ? -1 : 1)
  return clampSpanToDomain({ min: visible.min + delta, max: visible.max + delta }, domain)
}

/** Zoom about the window centre, clamped to the domain and to a minimum span. */
export function zoomSpanAboutCentre(
  visible: CanvasSpan,
  domain: CanvasSpan,
  factor: number,
  minSpan: number,
): CanvasSpan {
  const span = visible.max - visible.min
  const centre = (visible.min + visible.max) / 2
  const half = Math.max((span * factor) / 2, minSpan / 2)
  return clampSpanToDomain({ min: centre - half, max: centre + half }, domain)
}

/**
 * The window a shift+drag selected, or null for a stray click. The minimum span exists so a
 * click-with-shift cannot zoom the canvas to a sliver of noise.
 */
export function spanFromDrag(a: number, b: number, minSpan: number): CanvasSpan | null {
  const min = Math.min(a, b)
  const max = Math.max(a, b)
  if (!Number.isFinite(min) || !Number.isFinite(max)) return null
  if (max - min < minSpan) return null
  return { min, max }
}

/** True when a pointer-down is the explicit zoom-window chord rather than a pan. */
export function isZoomWindowChord(event: { shiftKey: boolean }): boolean {
  return event.shiftKey
}

export type CanvasKeyAction =
  | { kind: "pan"; screenDirection: -1 | 1 }
  | { kind: "zoom"; factor: number }
  | { kind: "reset" }

/**
 * The shared keymap. Escape is deliberately absent: cancelling a transient gesture is viewer
 * state (which drag ref, which menu), so each viewer handles it — but none may map Esc to reset.
 */
export function canvasKeyAction(key: string): CanvasKeyAction | null {
  switch (key) {
    case "ArrowLeft":
      return { kind: "pan", screenDirection: -1 }
    case "ArrowRight":
      return { kind: "pan", screenDirection: 1 }
    case "+":
    case "=":
      return { kind: "zoom", factor: CANVAS_ZOOM_IN_FACTOR }
    case "-":
    case "_":
      return { kind: "zoom", factor: CANVAS_ZOOM_OUT_FACTOR }
    case "0":
      return { kind: "reset" }
    default:
      return null
  }
}

/**
 * Multiplicative intensity step for one wheel event. Exponential in deltaY so a notch is a
 * constant *ratio* regardless of direction, and trackpad micro-deltas make micro-adjustments.
 * Scroll up (negative deltaY) grows the peaks. Callers clamp with CANVAS_INTENSITY_MIN/MAX.
 */
export function wheelIntensityFactor(deltaY: number): number {
  return Math.exp(-deltaY * 0.0015)
}

/** The one hover-readout format: δ to 3 dp, matching the precision the backend reports. */
export function formatHoverPpm(ppm: number): string {
  return `δ ${ppm.toFixed(3)} ppm`
}

/** Intensity half of the readout — exponent form, since raw FID intensities span decades. */
export function formatHoverIntensity(intensity: number): string {
  return `I ${intensity.toExponential(2)}`
}

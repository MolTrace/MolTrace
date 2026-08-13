/**
 * Generates components/marketing/orbital-field.css — the particle field behind
 * the evidence section, as six background layers.
 *
 * WHY THIS IS A STYLESHEET AND NOT INLINE STYLES. The field is ~730 dots, which
 * is ~31KB of data URI. As `style={{ backgroundImage }}` on a server component
 * that shipped TWICE in every HTML response: once in the element's style
 * attribute and once again in the RSC flight payload React streams for
 * hydration. Measured on the homepage that was 85KB of a 275KB document — 32% of
 * the page, for decoration, re-downloaded on every navigation.
 *
 * In a stylesheet it appears once, in a file the browser caches across every
 * page on the site, and the HTML carries six empty divs.
 *
 * The animation timings live here too, for the same reason: emitting them as
 * inline style props would put six more strings into the flight payload for no
 * benefit. The component ends up rendering pure class names and nothing else.
 *
 * Run after changing BAND_SPEC:  node scripts/generate-orbital-field.mjs
 */

import { writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..")
const OUT = join(ROOT, "components", "marketing", "orbital-field.css")

const VIEW_W = 1200
const VIEW_H = 600
const CENTRE_X = VIEW_W / 2
const CENTRE_Y = VIEW_H / 2

const PLAIN = "#E6EEF8"
const TINT = "#7AA7FF"

/** Deterministic PRNG, so regenerating produces a byte-identical file. */
function mulberry32(seed) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/**
 * Six bands, inner radius deliberately large: the heading and the cards sit in
 * the middle of the section, so the field has to be a ring around them rather
 * than a cloud over them. Counts scale with circumference, which keeps the
 * density even — a fixed count per band crowds the inner ones and thins the
 * outer ones.
 *
 * Durations are all different and directions alternate, which is what makes a
 * rotating point cloud read as a drifting field rather than one rigid wheel:
 * neighbouring dots separate slowly instead of moving together.
 */
const BAND_SPEC = [
  { inner: 290, outer: 350, count: 96, duration: 150, reverse: false },
  { inner: 350, outer: 410, count: 112, duration: 195, reverse: true },
  { inner: 410, outer: 470, count: 124, duration: 250, reverse: false },
  { inner: 470, outer: 530, count: 132, duration: 315, reverse: true },
  { inner: 530, outer: 600, count: 140, duration: 390, reverse: false },
  { inner: 600, outer: 680, count: 128, duration: 480, reverse: true },
]

/** Opacity rounded to one of six steps, so dots can share a group. */
const opacityStep = (o) => (Math.round(o * 6) / 6).toFixed(2)

/**
 * One band as an SVG data URI, encoded tightly.
 *
 * Colour and opacity are hoisted onto parent `<g>` elements rather than repeated
 * on every circle, coordinates round to whole units (the field is 1200 wide;
 * sub-pixel placement is invisible), and only `#`, `<` and `>` are escaped —
 * encodeURIComponent would also escape the quotes, spaces, slashes and equals
 * signs that make up most of the string, inflating it by about 65% for nothing.
 * Single quotes throughout so no quote needs escaping at all.
 */
function bandImage(particles) {
  const buckets = new Map()
  for (const p of particles) {
    const key = `${p.tint ? TINT : PLAIN}|${opacityStep(p.o)}`
    const bucket = buckets.get(key)
    if (bucket) bucket.push(p)
    else buckets.set(key, [p])
  }

  const groups = [...buckets]
    .map(([key, dots]) => {
      const [fill, opacity] = key.split("|")
      const circles = dots
        .map((p) => `<circle cx='${Math.round(p.x)}' cy='${Math.round(p.y)}' r='${p.r.toFixed(1)}'/>`)
        .join("")
      return `<g fill='${fill}' opacity='${opacity}'>${circles}</g>`
    })
    .join("")

  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 ${VIEW_W} ${VIEW_H}'>${groups}</svg>`
  return svg.replace(/#/g, "%23").replace(/</g, "%3C").replace(/>/g, "%3E")
}

function build() {
  const rand = mulberry32(0xa11ce)
  return BAND_SPEC.map((spec) => {
    const particles = Array.from({ length: spec.count }, () => {
      const angle = rand() * Math.PI * 2
      const radius = spec.inner + rand() * (spec.outer - spec.inner)
      const depth = rand()
      return {
        x: CENTRE_X + Math.cos(angle) * radius,
        y: CENTRE_Y + Math.sin(angle) * radius,
        r: 1 + depth * 1.5,
        o: 0.3 + depth * 0.65,
        // A scatter of cool-tinted particles, as in the reference. Rare enough
        // to read as a highlight rather than a second colour in the palette.
        tint: rand() < 0.09,
      }
    })
    return { ...spec, particles, image: bandImage(particles) }
  })
}

const bands = build()

const layers = bands
  .map(
    (band, i) => `
.mt-orbit-${i + 1} {
  background-image: url("data:image/svg+xml,${band.image}");
  animation-duration: ${band.duration}s;
  animation-direction: ${band.reverse ? "reverse" : "normal"};
}`,
  )
  .join("\n")

const css = `/* GENERATED by scripts/generate-orbital-field.mjs — do not edit by hand.
   Re-run that script after changing BAND_SPEC.

   ${bands.reduce((n, b) => n + b.particles.length, 0)} particles across ${bands.length} layers. Each layer is ONE element carrying a
   pre-rendered background, so the per-frame cost is a composited transform of an
   existing texture and does not grow with dot count. Rendering the dots as DOM
   elements instead would look identical and put hundreds of nodes into the style
   and layout trees. */

/* The backdrop's own horizon. Inline it would be another string in the flight
   payload for something that never changes. */
.mt-orbit-sky {
  background: radial-gradient(115% 85% at 50% 50%, #0e1a2c 0%, #080e18 45%, #05070c 100%);
}

.mt-orbit {
  position: absolute;
  inset: 0;
  background-position: center;
  background-repeat: no-repeat;
  /* cover, not 100% 100%: the field is authored 2:1, and scaling the axes
     independently would turn every round dot into an oval. */
  background-size: cover;
  animation-name: mt-orbit-spin;
  animation-timing-function: linear;
  animation-iteration-count: infinite;
  will-change: transform;
}

@keyframes mt-orbit-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* Ambient, endless, decorative motion — exactly what this setting is for. The
   field stays, it simply stops turning. */
@media (prefers-reduced-motion: reduce) {
  .mt-orbit {
    animation: none;
    will-change: auto;
  }
}
${layers}
`

writeFileSync(OUT, css, "utf8")
console.log(
  `  wrote ${OUT.split("/").slice(-2).join("/")} — ${bands.reduce((n, b) => n + b.particles.length, 0)} particles, ${(css.length / 1024).toFixed(1)} KB`,
)

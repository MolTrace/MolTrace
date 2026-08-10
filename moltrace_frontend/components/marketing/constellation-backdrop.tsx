/**
 * The night-sky backdrop behind the evidence section — and a constellation
 * rather than a starfield, because the section is about a chain.
 *
 * A plain field of dots would be decoration borrowed from somebody else's
 * landing page. What this draws is a trail: scattered stars, then a line linking
 * a handful of them into a path with brighter waypoints along it, and a pulse
 * that travels the path end to end. That is the claim the section makes in words
 * — entries chained, references named, signatures bound, all of it re-walkable —
 * drawn behind the words that make it.
 *
 * EVERYTHING IS DETERMINISTIC. The stars come from a seeded PRNG evaluated once
 * at module scope, never Math.random() during render. A random layout would
 * differ between the server pass and the client pass and hydrate into a mismatch
 * — and the failure is nasty precisely because it looks fine: React patches the
 * DOM, the page works, and the only symptom is a console error and a double
 * paint. Seeded, the two passes agree by construction.
 *
 * It is decorative and marked aria-hidden. Nothing here carries meaning a reader
 * needs, and the section's argument is entirely in its text.
 */

/** Deterministic PRNG — same sequence every call, on both sides of hydration. */
function mulberry32(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/**
 * A wide viewBox with `slice`, not a 0-100 box stretched to fit. Stretching a
 * square coordinate space across a wide band turns every circle into an ellipse
 * — stars go visibly oval on a desktop viewport. Slicing keeps them round and
 * crops the overflow, which for a backdrop is free.
 */
const VIEW_W = 1200
const VIEW_H = 600

export type Star = { x: number; y: number; r: number; o: number; delay: number; dur: number }

/**
 * Exported so determinism can actually be tested. The module-level STARS below
 * is computed once, which means rendering the component twice compares one array
 * to itself and would pass even if this used Math.random — a test that cannot
 * fail. Calling this twice is the real check.
 */
export function generateStars(count = 110): Star[] {
  const rand = mulberry32(0x5eed)
  return Array.from({ length: count }, () => {
    // Radius and brightness move together, so the field reads as depth rather
    // than as dots of arbitrary size — a big faint star looks like a smudge.
    // Position draws separately from depth; sharing a draw would deterministically
    // arrange every star along one diagonal.
    const depth = rand()
    return {
      x: rand() * VIEW_W,
      y: rand() * VIEW_H,
      r: 0.6 + depth * 1.5,
      o: 0.18 + depth * 0.55,
      delay: rand() * 7,
      dur: 3.5 + rand() * 4.5,
    }
  })
}

const STARS: Star[] = generateStars()

/**
 * The trail. Hand-placed rather than generated: a random walk wanders and
 * doubles back, and this needs to read left-to-right as one continuous path with
 * a gentle rise, which is a shape you choose rather than sample.
 */
const TRAIL = "M -40 392 L 158 338 L 342 366 L 522 286 L 706 316 L 884 242 L 1058 268 L 1240 206"

/** Waypoints — the linked records. Brighter, haloed, spaced under the cards. */
const WAYPOINTS = [
  { x: 158, y: 338 },
  { x: 522, y: 286 },
  { x: 884, y: 242 },
]

export function ConstellationBackdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      {/* Deep-space base. The blue is lifted toward the top so the band has a
          horizon rather than being a flat rectangle of black. */}
      <div className="absolute inset-0 bg-[#05070c]" />
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(120% 90% at 50% -10%, #12233a 0%, #0a1220 42%, #05070c 100%)",
        }}
      />

      <svg
        className="absolute inset-0 h-full w-full"
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        preserveAspectRatio="xMidYMid slice"
        aria-hidden
        focusable="false"
      >
        <defs>
          {/* The trail brightens toward the middle and fades at both ends, so it
              reads as a path continuing past the section rather than as a line
              that starts and stops at the edges of a box. */}
          <linearGradient id="mt-trail" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#00DFA0" stopOpacity="0" />
            <stop offset="18%" stopColor="#00DFA0" stopOpacity="0.32" />
            <stop offset="82%" stopColor="#26C6FF" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#26C6FF" stopOpacity="0" />
          </linearGradient>
          <radialGradient id="mt-waypoint">
            <stop offset="0%" stopColor="#7DF5D0" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#7DF5D0" stopOpacity="0" />
          </radialGradient>
        </defs>

        {STARS.map((star, index) => (
          <circle
            key={index}
            cx={star.x}
            cy={star.y}
            r={star.r}
            fill="#CFE6FF"
            // The attribute is the resting brightness AND the reduced-motion
            // fallback; the custom property is what the keyframe dims from, so
            // each star twinkles around its own level instead of every star
            // pulsing to the same one.
            opacity={star.o}
            className="mt-star"
            style={
              {
                "--mt-star-o": star.o,
                animationDelay: `${star.delay}s`,
                animationDuration: `${star.dur}s`,
              } as React.CSSProperties
            }
          />
        ))}

        <path d={TRAIL} fill="none" stroke="url(#mt-trail)" strokeWidth={1.25} />

        {WAYPOINTS.map((point) => (
          <g key={`${point.x}-${point.y}`}>
            <circle cx={point.x} cy={point.y} r={16} fill="url(#mt-waypoint)" />
            <circle cx={point.x} cy={point.y} r={2.4} fill="#9FF7DC" opacity={0.9} />
          </g>
        ))}

        {/* The pulse: one short dash walking the path. `pathLength` normalises
            the geometry to 1000 units so the dash pattern does not have to be
            recomputed whenever the path is edited. */}
        <path
          className="mt-trail-pulse"
          d={TRAIL}
          fill="none"
          stroke="#7DF5D0"
          strokeWidth={1.6}
          strokeLinecap="round"
          pathLength={1000}
          strokeDasharray="70 930"
        />
      </svg>

      {/* Softens the join where the band meets the sections above and below, so
          the dark does not land as a hard horizontal seam across the page. */}
      <div className="absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-[#05070c] to-transparent" />
      <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-[#05070c] to-transparent" />
    </div>
  )
}

"use client"

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react"
import {
  AlertTriangle,
  Atom,
  BarChart3,
  BookCheck,
  Check,
  ChevronLeft,
  ChevronRight,
  FileCheck,
  FlaskConical,
  ScanSearch,
  Sparkles,
  Target,
  Waves,
  X,
} from "lucide-react"

// ─────────────────────────────────────────────────────────────────────────────
// MODULE "EXPLORE" OVERLAYS — lazy-loaded chunk.
//
// These three interactive overlays (Spectroscopy carousel · Regulatory QA-RAG
// snippet · Reaction 3D response surface) plus their helpers (inline spectrum
// SVGs, the drag/keyboard carousel, the response-surface viz) account for ~half
// of the original module-cards source. They only ever render after a user clicks
// "Explore Module", so they are split out here and pulled in via next/dynamic
// (ssr:false) from module-cards.tsx — keeping them OUT of the homepage's initial
// JS payload. Nothing here is imported on first paint.
// ─────────────────────────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────────────────
// Each spectrum SVG below is RESPONSIVE: viewBox + className "w-full h-auto"
// so the figure fills its column without horizontal-scroll inside the slide.
// All horizontal navigation now happens at the carousel level (one slide at a
// time, drag/scroll/wheel/arrow-key snaps between 1H NMR → 13C NMR → LC-MS).
// ─────────────────────────────────────────────────────────────────────────────

// 1H NMR — multiplets retained (J-coupling produces real multiplet shapes).
//   • singlet at 9.5 ppm (aldehyde)
//   • singlet at 7.26 (CDCl₃ residual / Ar)
//   • quartet at 4.13 (OCH₂)
//   • triplet at 1.26 (CH₃)
//   • TMS at 0
function OneHNmrSvg() {
  return (
    <svg
      viewBox="0 0 1000 320"
      preserveAspectRatio="xMidYMid meet"
      className="block w-full h-auto select-none"
      role="img"
      aria-label="Resolved 1H NMR spectrum: aldehyde 9.5, aromatic 7.26, OCH2 quartet 4.13, CH3 triplet 1.26, TMS 0"
    >
      <defs>
        <linearGradient id="nmr1hFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgb(20 184 166)" stopOpacity="0.28" />
          <stop offset="100%" stopColor="rgb(20 184 166)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* Major / minor gridlines */}
      <g stroke="currentColor" strokeOpacity="0.08" strokeWidth="0.6">
        {[100, 200, 300, 400, 500, 600, 700, 800, 900, 980].map((x) => (
          <line key={x} x1={x} y1="40" x2={x} y2="270" />
        ))}
        <line x1="0" y1="270" x2="1000" y2="270" strokeOpacity="0.2" />
      </g>
      {/* Spectrum trace (10 ppm at left → 0 ppm at right) */}
      <path
        d="
          M 20 270 L 100 270
          L 130 268 L 145 250 L 152 220 L 156 188 L 159 220 L 165 250 L 175 268 L 200 270
          L 260 270 L 290 270
          L 300 264 L 312 240 L 318 130 L 322 240 L 328 264 L 340 268
          L 380 270
          L 410 270 L 420 268
          L 440 248 L 446 200 L 452 152 L 456 80 L 460 152 L 466 200 L 472 248 L 480 268
          L 520 270
          L 580 270
          L 640 270
          L 700 270
          L 740 270
          L 760 268 L 800 264
          L 820 256 L 830 230 L 840 256 L 845 268
          L 855 256 L 862 200 L 866 142 L 870 78 L 874 142 L 878 200 L 884 256 L 894 268
          L 905 256 L 912 230 L 920 256 L 925 268
          L 945 270
          L 960 264 L 964 248 L 970 264 L 974 270
          L 1000 270
          Z
        "
        fill="url(#nmr1hFill)"
        stroke="rgb(20 184 166)"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      {/* Peak labels */}
      <g fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace" fontSize="11" fill="currentColor" fillOpacity="0.78">
        <text x="158" y="178" textAnchor="middle">9.5 (s)</text>
        <text x="318" y="120" textAnchor="middle">7.26</text>
        <text x="456" y="68" textAnchor="middle">4.13 (q)</text>
        <text x="870" y="66" textAnchor="middle">1.26 (t)</text>
        <text x="970" y="232" textAnchor="middle">0.0 TMS</text>
      </g>
      {/* X-axis labels */}
      <g
        fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
        fontSize="11"
        fill="currentColor"
        fillOpacity="0.55"
      >
        {[
          [100, "10"],
          [200, "9"],
          [300, "8"],
          [400, "7"],
          [500, "6"],
          [600, "5"],
          [700, "4"],
          [800, "3"],
          [900, "2"],
          [980, "1"],
        ].map(([x, label]) => (
          <text key={x} x={x as number} y="290" textAnchor="middle">
            {label}
          </text>
        ))}
        <text x="500" y="310" textAnchor="middle" fillOpacity="0.55">δ (ppm)</text>
      </g>
    </svg>
  )
}

// ¹³C NMR — proton-decoupled, every unique carbon resolves to a singlet.
//   • thin vertical PEAKS (no circle caps — that was reading as a chromatogram)
//   • signature CDCl₃ triplet at δ 77.0 (3 close singlets, ~equal height) —
//     this is the visual fingerprint that makes a 13C unmistakably a 13C
//   • subtle ringing baseline so it reads as real instrument data
//   • δ-prefixed ppm labels (NMR convention) with tiny assignment underneath
function ThirteenCNmrSvg() {
  // [x, height (px), δ (ppm) label, assignment]
  const PEAKS: Array<[number, number, string, string]> = [
    [110, 215, "205.3", "C=O"],
    [255, 235, "170.2", "COOR"],
    [488, 200, "132.1", "Ar"],
    [528, 195, "128.4", "Ar"],
    [718, 175, "68.6", "OCH"],
    [858, 165, "22.1", "CH₃"],
    [955, 78, "0.0", "TMS"],
  ]
  // CDCl₃ residual — characteristic 1:1:1 triplet at δ 77.0 (J ≈ 32 Hz).
  // Three thin closely-spaced lines of (very nearly) equal height — this is
  // the single most recognizable feature of a real ¹³C{¹H} spectrum.
  const CDCL3_X: [number, number, number] = [620, 632, 644]
  const CDCL3_H = 110
  const BASE = 270
  return (
    <svg
      viewBox="0 0 1000 320"
      preserveAspectRatio="xMidYMid meet"
      className="block w-full h-auto select-none"
      role="img"
      aria-label="Decoupled 13C NMR spectrum: carbonyl 205, COOR 170, aromatic 128 and 132, CDCl3 triplet 77, OCH 68, CH3 22, TMS 0"
    >
      <g stroke="currentColor" strokeOpacity="0.08" strokeWidth="0.6">
        {[100, 200, 300, 400, 500, 600, 700, 800, 900, 980].map((x) => (
          <line key={x} x1={x} y1="40" x2={x} y2={BASE} />
        ))}
      </g>
      {/* Subtle ringing baseline (very small zigzag) instead of a flat line */}
      <path
        d="M 0 270.6 L 70 270.2 L 140 270.7 L 210 270.4 L 280 270.6 L 350 270.3 L 420 270.7 L 490 270.5 L 560 270.4 L 630 270.6 L 700 270.5 L 770 270.4 L 840 270.6 L 910 270.5 L 980 270.4 L 1000 270.6"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.22"
        strokeWidth="0.7"
      />
      {/* Main peaks — thin vertical lines, square ends, no circle caps */}
      <g stroke="rgb(20 184 166)" strokeWidth="1.4" strokeLinecap="square">
        {PEAKS.map(([x, h]) => (
          <line key={x} x1={x} y1={BASE} x2={x} y2={BASE - h} />
        ))}
        {CDCL3_X.map((x) => (
          <line key={`cd-${x}`} x1={x} y1={BASE} x2={x} y2={BASE - CDCL3_H} />
        ))}
      </g>
      {/* Peak labels — δ value above, assignment below */}
      <g fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace" fontSize="11" fill="currentColor">
        {PEAKS.map(([x, h, label, sub]) => (
          <g key={`lbl-${x}`}>
            <text x={x} y={BASE - h - 22} textAnchor="middle" fillOpacity="0.78">
              δ {label}
            </text>
            <text x={x} y={BASE - h - 9} textAnchor="middle" fontSize="9" fillOpacity="0.55">
              {sub}
            </text>
          </g>
        ))}
        {/* CDCl₃ triplet label centered over the 3 close lines */}
        <text x={CDCL3_X[1]} y={BASE - CDCL3_H - 22} textAnchor="middle" fillOpacity="0.78">
          δ 77.0
        </text>
        <text x={CDCL3_X[1]} y={BASE - CDCL3_H - 9} textAnchor="middle" fontSize="9" fillOpacity="0.55">
          CDCl₃
        </text>
      </g>
      {/* X-axis: 210 → 0 ppm (NMR convention: high field on right) */}
      <g
        fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
        fontSize="11"
        fill="currentColor"
        fillOpacity="0.55"
      >
        {[
          [85, "210"],
          [255, "170"],
          [415, "130"],
          [575, "90"],
          [735, "50"],
          [895, "10"],
          [970, "0"],
        ].map(([x, label]) => (
          <text key={x} x={x as number} y="290" textAnchor="middle">
            {label}
          </text>
        ))}
        <text x="500" y="310" textAnchor="middle" fillOpacity="0.55">δ (ppm)</text>
      </g>
    </svg>
  )
}

// LC-MS chromatogram — narrow Gaussian peaks (visibly chromatographic), not
// pure sticks. Each peak has a clear FWHM that distinguishes it from the ¹³C
// stick plot above. m/z + RT annotated above each peak.
function LcmsChromatogramSvg() {
  // [x center, height, m/z, RT, half-width-at-baseline (px)]
  const PEAKS: Array<[number, number, string, string, number]> = [
    [130, 195, "m/z 195", "4.2", 16],
    [305, 230, "m/z 251", "8.7", 18],
    [510, 245, "m/z 343", "14.3", 20],
    [725, 235, "m/z 412", "21.5", 19],
    [880, 200, "m/z 487", "26.1", 17],
  ]
  const BASE = 270
  return (
    <svg
      viewBox="0 0 1000 320"
      preserveAspectRatio="xMidYMid meet"
      className="block w-full h-auto select-none"
      role="img"
      aria-label="LC-MS total ion chromatogram (TIC): 5 m/z features at retention times 4.2, 8.7, 14.3, 21.5, 26.1 minutes"
    >
      <defs>
        <linearGradient id="lcmsFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgb(20 184 166)" stopOpacity="0.32" />
          <stop offset="100%" stopColor="rgb(20 184 166)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <g stroke="currentColor" strokeOpacity="0.08" strokeWidth="0.6">
        {[100, 200, 300, 400, 500, 600, 700, 800, 900, 980].map((x) => (
          <line key={x} x1={x} y1="40" x2={x} y2={BASE} />
        ))}
        <line x1="0" y1={BASE} x2="1000" y2={BASE} strokeOpacity="0.2" />
      </g>
      {/* Continuous baseline trace with each Gaussian peak inline */}
      <path
        d={(() => {
          // Construct one continuous path that traces baseline → up each
          // Gaussian → down → baseline → next peak → ... so the fill reads
          // as one TIC trace (not 5 disconnected polygons).
          let d = `M 20 ${BASE}`
          for (const [x, h, , , w] of PEAKS) {
            // baseline up to ~half-width-before peak
            d += ` L ${x - w} ${BASE}`
            // smooth Gaussian: cubic Bezier up to apex
            d += ` C ${x - w + 4} ${BASE}, ${x - 4} ${BASE - h}, ${x} ${BASE - h}`
            // and down again to baseline
            d += ` C ${x + 4} ${BASE - h}, ${x + w - 4} ${BASE}, ${x + w} ${BASE}`
          }
          d += ` L 980 ${BASE} L 980 ${BASE} L 20 ${BASE} Z`
          return d
        })()}
        fill="url(#lcmsFill)"
        stroke="rgb(20 184 166)"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      {/* m/z + RT labels above each peak apex */}
      <g fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace" fontSize="11" fill="currentColor">
        {PEAKS.map(([x, h, mz, rt]) => (
          <g key={`lbl-${x}`}>
            <text x={x} y={BASE - h - 22} textAnchor="middle" fillOpacity="0.78">
              {mz}
            </text>
            <text x={x} y={BASE - h - 9} textAnchor="middle" fontSize="9" fillOpacity="0.55">
              RT {rt}
            </text>
          </g>
        ))}
      </g>
      {/* X-axis: retention time in minutes */}
      <g
        fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
        fontSize="11"
        fill="currentColor"
        fillOpacity="0.55"
      >
        {[
          [100, "4"],
          [260, "8"],
          [420, "12"],
          [580, "16"],
          [740, "21"],
          [900, "26"],
          [980, "30"],
        ].map(([x, label]) => (
          <text key={x} x={x as number} y="290" textAnchor="middle">
            {label}
          </text>
        ))}
        <text x="500" y="310" textAnchor="middle" fillOpacity="0.55">retention time (min)</text>
      </g>
    </svg>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Carousel slide: a single full-width frame containing the bulleted body text
// (left) and one large spectrum figure (right). They flow together — when the
// user scrolls horizontally, the figure AND its text move as one slide.
// ─────────────────────────────────────────────────────────────────────────────
type SlideDef = {
  // eyebrow + title accept JSX so we can render isotope superscripts (¹H, ¹³C)
  // via <sup> instead of relying on Unicode glyphs that render inconsistently
  // across user fonts.
  eyebrow: ReactNode
  title: ReactNode
  subtitle: string
  bullets: string[]
  footer: ReactNode
  icon: typeof Waves
  // Plain-text label used for ARIA names and indicator-button labels (where
  // we need a string, not JSX).
  figureLabel: string
  figure: ReactNode
}

function CarouselSlide({
  index,
  total,
  eyebrow,
  title,
  subtitle,
  bullets,
  footer,
  icon: Icon,
  figureLabel,
  figure,
}: SlideDef & { index: number; total: number }) {
  return (
    <article
      className="snap-center shrink-0 basis-full px-1"
      aria-roledescription="slide"
      aria-label={`${figureLabel} — slide ${index + 1} of ${total}`}
      data-slide-label={figureLabel}
    >
      <div className="grid items-stretch gap-6 lg:grid-cols-12 lg:gap-8">
        {/* Bulleted body text */}
        <div className="lg:col-span-5 lg:py-2">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-teal-600 dark:text-teal-400">
            {eyebrow} · {String(index + 1).padStart(2, "0")} / {String(total).padStart(2, "0")}
          </p>
          <h4 className="mt-2 inline-flex items-center gap-2 text-xl font-bold tracking-tight sm:text-2xl">
            <Icon className="h-5 w-5 text-teal-500 dark:text-teal-400" aria-hidden />
            {title}
          </h4>
          <p className="mt-1 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            {subtitle}
          </p>
          <ul className="mt-5 space-y-3">
            {bullets.map((b, i) => (
              <li key={i} className="flex items-start gap-2.5 text-sm leading-snug text-foreground/90">
                <Check
                  className="mt-0.5 h-3.5 w-3.5 shrink-0 text-teal-500 dark:text-teal-400"
                  strokeWidth={2.5}
                />
                <span>{b}</span>
              </li>
            ))}
          </ul>
          <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            {footer}
          </div>
        </div>
        {/* Enlarged figure */}
        <div className="lg:col-span-7">
          <div className="overflow-hidden rounded-xl border border-t-[3px] border-t-teal-500 bg-card p-4 shadow-sm dark:border-t-teal-400">
            {figure}
          </div>
        </div>
      </div>
    </article>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Horizontal snap-carousel that holds the 3 slides.
//
// Behavior:
//   • Auto-plays — advances one slide every 5s, looping 1 → 2 → 3 → 1.
//   • Auto-play STOPS PERMANENTLY the first time the user interacts manually
//     (drag, wheel, key, or pagination button). This is a once-on/once-off
//     latch — there is no resume, no hover-pause; once the user takes the
//     wheel they keep it.
//   • Wheel + pointer drag + arrow keys all advance one slide at a time.
//   • Escape hatch for tests: ?autoplay=0 in the URL disables auto-play so
//     deterministic assertions don't race against an auto-advance.
// ─────────────────────────────────────────────────────────────────────────────
const AUTOPLAY_INTERVAL_MS = 5_000

function SpectrumCarousel({ slides }: { slides: SlideDef[] }) {
  const ref = useRef<HTMLDivElement>(null)
  const [activeIdx, setActiveIdx] = useState(0)
  const [grabbing, setGrabbing] = useState(false)
  // Auto-play is a once-on/once-off latch. Defaults to ON; flipped OFF by
  // (a) the ?autoplay=0 URL escape hatch, or (b) the first manual gesture.
  const [autoplayActive, setAutoplayActive] = useState(true)
  const drag = useRef<{ active: boolean; startX: number; scrollLeft: number }>({
    active: false,
    startX: 0,
    scrollLeft: 0,
  })

  // Honor ?autoplay=0 escape hatch on mount
  useEffect(() => {
    if (typeof window === "undefined") return
    const flag = new URLSearchParams(window.location.search).get("autoplay")
    if (flag === "0" || flag === "false" || flag === "off") {
      setAutoplayActive(false)
    }
  }, [])

  // Stable callback to permanently stop auto-play once the user takes over.
  const stopAutoplay = useCallback(() => setAutoplayActive(false), [])

  // Wheel: redirect vertical wheel/trackpad to horizontal pan across slides.
  // First wheel event also stops auto-play.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) return
      e.preventDefault()
      setAutoplayActive(false)
      el.scrollLeft += e.deltaY
    }
    el.addEventListener("wheel", onWheel, { passive: false })
    return () => el.removeEventListener("wheel", onWheel)
  }, [])

  // Track which slide is currently centered (for indicator + nav state)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    let raf = 0
    const tick = () => {
      const w = el.clientWidth
      if (w <= 0) return
      const idx = Math.round(el.scrollLeft / w)
      setActiveIdx(Math.max(0, Math.min(slides.length - 1, idx)))
    }
    const onScroll = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(tick)
    }
    el.addEventListener("scroll", onScroll, { passive: true })
    tick()
    return () => {
      el.removeEventListener("scroll", onScroll)
      cancelAnimationFrame(raf)
    }
  }, [slides.length])

  // Auto-play loop: advance one slide every AUTOPLAY_INTERVAL_MS, wrapping at
  // the end. Disabled when autoplayActive is false. We programmatically
  // scrollTo() — which fires the scroll listener above and updates activeIdx
  // naturally, but does NOT call stopAutoplay() (only direct user gestures
  // do that).
  useEffect(() => {
    if (!autoplayActive) return
    const id = window.setInterval(() => {
      const el = ref.current
      if (!el) return
      const w = el.clientWidth
      if (w <= 0) return
      const cur = Math.round(el.scrollLeft / w)
      const next = (cur + 1) % slides.length
      el.scrollTo({ left: next * w, behavior: "smooth" })
    }, AUTOPLAY_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [autoplayActive, slides.length])

  const gotoSlide = useCallback(
    (idx: number, viaUser = true) => {
      const el = ref.current
      if (!el) return
      if (viaUser) setAutoplayActive(false)
      const i = Math.max(0, Math.min(slides.length - 1, idx))
      el.scrollTo({ left: i * el.clientWidth, behavior: "smooth" })
      setActiveIdx(i)
    },
    [slides.length],
  )

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const el = ref.current
      if (!el) return
      stopAutoplay()
      drag.current.active = true
      drag.current.startX = e.clientX
      drag.current.scrollLeft = el.scrollLeft
      el.setPointerCapture(e.pointerId)
      setGrabbing(true)
    },
    [stopAutoplay],
  )

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!drag.current.active || !ref.current) return
    const dx = e.clientX - drag.current.startX
    ref.current.scrollLeft = drag.current.scrollLeft - dx
  }, [])

  const onPointerUp = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    drag.current.active = false
    if (ref.current?.hasPointerCapture(e.pointerId)) {
      ref.current.releasePointerCapture(e.pointerId)
    }
    setGrabbing(false)
  }, [])

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "ArrowRight") {
        e.preventDefault()
        gotoSlide(activeIdx + 1)
      } else if (e.key === "ArrowLeft") {
        e.preventDefault()
        gotoSlide(activeIdx - 1)
      } else if (e.key === "Home") {
        e.preventDefault()
        gotoSlide(0)
      } else if (e.key === "End") {
        e.preventDefault()
        gotoSlide(slides.length - 1)
      }
    },
    [activeIdx, gotoSlide, slides.length],
  )

  return (
    <div
      className="relative"
      data-autoplay-state={autoplayActive ? "playing" : "stopped"}
    >
      <div
        ref={ref}
        role="region"
        aria-roledescription="carousel"
        aria-label="Spectroscopy capabilities — auto-advancing; drag, scroll, or use arrow keys to take over"
        tabIndex={0}
        className="flex snap-x snap-mandatory overflow-x-auto overflow-y-hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40"
        style={{
          cursor: grabbing ? "grabbing" : "grab",
          scrollbarWidth: "thin",
          WebkitOverflowScrolling: "touch",
        }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onKeyDown={onKeyDown}
      >
        {slides.map((slide, i) => (
          <CarouselSlide key={i} index={i} total={slides.length} {...slide} />
        ))}
      </div>

      {/* Pagination row: prev — pill indicators — next */}
      <div className="mt-5 flex items-center justify-between gap-4">
        <button
          type="button"
          onClick={() => gotoSlide(activeIdx - 1)}
          disabled={activeIdx === 0}
          aria-label="Previous spectrum"
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border bg-background text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden />
        </button>
        <div className="flex items-center gap-2" role="tablist" aria-label="Spectrum indicators">
          {slides.map((s, i) => (
            <button
              key={i}
              type="button"
              role="tab"
              onClick={() => gotoSlide(i)}
              aria-label={`Show ${s.figureLabel}`}
              aria-selected={activeIdx === i}
              className={[
                "h-2 rounded-full transition-all duration-200",
                activeIdx === i
                  ? "w-10 bg-teal-500 dark:bg-teal-400"
                  : "w-4 bg-border hover:bg-muted-foreground/40",
              ].join(" ")}
            />
          ))}
        </div>
        <button
          type="button"
          onClick={() => gotoSlide(activeIdx + 1)}
          disabled={activeIdx === slides.length - 1}
          aria-label="Next spectrum"
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border bg-background text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40"
        >
          <ChevronRight className="h-4 w-4" aria-hidden />
        </button>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// The expanded interface that opens when "Explore Module" is clicked on
// Spectroscopy. Headline + brief framing, then a horizontal carousel of 3
// large slides — each slide pairs a bulleted writeup with one full-width
// figure (1H NMR → 13C NMR → LC-MS).
// ─────────────────────────────────────────────────────────────────────────────
export function SpectroscopyExploreInterface({ onClose }: { onClose: () => void }) {
  // Reused inline JSX bits so isotope superscripts (¹H, ¹³C) appear with
  // <sup> styling instead of leaning on the Unicode ¹ and ¹³ glyphs (some
  // user fonts render those at base-line height).
  const oneH = (
    <>
      <sup>1</sup>H
    </>
  )
  const thirteenC = (
    <>
      <sup>13</sup>C
    </>
  )

  const slides: SlideDef[] = [
    {
      eyebrow: (
        <>
          Spectroscopy · {oneH} NMR
        </>
      ),
      title: <>Resolved {oneH} NMR</>,
      subtitle: "CDCl₃ · 400 MHz · TMS @ 0.0 ppm",
      icon: Waves,
      figureLabel: "1H NMR",
      bullets: [
        "Automated deconvolution unwraps overlapping multiplets — a quartet hiding under a residual solvent stops sabotaging your quantification.",
        "FID processed in one pass: apodization, zero-filling, phase correction, and baseline drift handled before integration.",
        "Auto-referenced against a known standard so every chemical shift you publish is grounded in raw signal you can re-derive.",
        "Five multiplets resolved with USP <761>-ready integrations and confidence per peak.",
      ],
      footer: (
        <>
          <span>5 multiplets</span>
          <span className="text-teal-600 dark:text-teal-400">SNR 240</span>
        </>
      ),
      figure: <OneHNmrSvg />,
    },
    {
      eyebrow: (
        <>
          Spectroscopy · {thirteenC} NMR
        </>
      ),
      title: <>Decoupled {thirteenC} NMR</>,
      subtitle: "CDCl₃ · 100 MHz · WALTZ-16 decoupled",
      icon: Atom,
      figureLabel: "13C NMR",
      bullets: [
        "Proton-decoupled acquisition — every unique carbon resolves as a single sharp peak at its exact chemical shift.",
        "Signature CDCl₃ triplet at δ 77.0 anchors the spectrum — the visual fingerprint of a real ¹³C{¹H} acquisition.",
        "DEPT-135 paired in the same run confirms CH₃ / CH₂ / CH multiplicity without a second sample.",
        "Six unique carbons mapped against the predicted skeleton — Δδ ±0.05 ppm vs. computed shifts.",
      ],
      footer: (
        <>
          <span>6 carbons</span>
          <span className="text-teal-600 dark:text-teal-400">DEPT confirmed</span>
        </>
      ),
      figure: <ThirteenCNmrSvg />,
    },
    {
      eyebrow: (
        <>
          Spectroscopy · LC-MS
        </>
      ),
      title: <>LC-MS chromatogram (TIC)</>,
      subtitle: "ESI+ · 30 min gradient · m/z annotated",
      icon: BarChart3,
      figureLabel: "LC-MS",
      bullets: [
        "Total Ion Chromatogram across a 30-minute gradient — features above the s/n threshold flagged automatically.",
        "Each retention-time peak is m/z-annotated with ±0.02 min reproducibility versus your method standard.",
        "MS² fragmentation queued against your in-house spectral library; unknown features surface for de-novo annotation.",
        "Five features auto-tagged — ready to flow straight into the regulatory dossier and impurity tables.",
      ],
      footer: (
        <>
          <span>5 features</span>
          <span className="text-teal-600 dark:text-teal-400">RT ±0.02 min</span>
        </>
      ),
      figure: <LcmsChromatogramSvg />,
    },
  ]

  return (
    <div
      className="rounded-xl border border-t-[3px] border-t-teal-500 bg-card p-7 shadow-sm dark:border-t-teal-400"
      role="region"
      aria-label="Spectroscopy Intelligence — explore the resolved spectra"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-teal-600 dark:text-teal-400">
            Spectroscopy Intelligence · Live preview
          </p>
          <h3 className="text-2xl font-bold tracking-tight sm:text-3xl">
            Uncover the Ground Truth in Your Data.
          </h3>
          <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground sm:text-base">
            Three spectra, one continuous picture of your molecule.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close explore preview"
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border bg-background text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>

      <div className="mt-6">
        <SpectrumCarousel slides={slides} />
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// REGULATORY INTELLIGENCE HUB — explore overlay
//
// Headline: "Built-in Compliance and Safety."
// Body (bulleted): How the QA-RAG system grounds every answer in
//   EPA / FDA / ICH / EMA / REACH guidance, jurisdiction-aware risk
//   thresholds, and the mandatory human reviewer gate before findings can
//   ship to a dossier.
// Visual: A live-feel chat snippet — a chemist asks about an NDMA intake
//   limit, the QA-RAG answer cites multiple regulations + flags a Class 1
//   mutagen warning. Composed as plain JSX (no SVG) since the visual mimics
//   our actual chat UI.
// ─────────────────────────────────────────────────────────────────────────────
function RegulatoryQaRagSnippet() {
  return (
    <div
      className="overflow-hidden rounded-xl border border-t-[3px] border-t-cyan-500 bg-card p-5 shadow-sm dark:border-t-cyan-400"
      role="img"
      aria-label="QA-RAG chat preview: chemist asks if NDMA at 110 ng per day is acceptable; AI responds with a flagged Class 1 mutagen warning citing ICH M7(R2), FDA, and EMA"
    >
      {/* Card header */}
      <div className="mb-4 flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-md border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-cyan-600 dark:text-cyan-400">
          <Sparkles className="h-3 w-3" aria-hidden />
          QA-RAG · Live answer
        </span>
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          v2.4 · 4 sources
        </span>
      </div>

      {/* User question bubble */}
      <div className="mb-4 flex items-start gap-3">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-bold uppercase tracking-wider">
          JC
        </div>
        <div className="flex-1 rounded-lg bg-muted/50 px-4 py-2.5">
          <p className="text-sm leading-snug">
            Can we ship NDMA at <span className="font-mono">110 ng/day</span> in this generic
            API? FDA filing.
          </p>
        </div>
      </div>

      {/* AI response */}
      <div className="flex items-start gap-3">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-cyan-500/15 text-cyan-600 dark:text-cyan-400">
          <ScanSearch className="h-3.5 w-3.5" aria-hidden />
        </div>
        <div className="flex-1 space-y-3">
          {/* Verdict + flagged toxicity warning */}
          <div className="rounded-lg border border-red-500/40 bg-red-500/5 p-4">
            <div className="flex items-start gap-2">
              <AlertTriangle
                className="mt-0.5 h-4 w-4 shrink-0 text-red-500 dark:text-red-400"
                aria-hidden
              />
              <div className="flex-1">
                <p className="text-sm font-bold text-red-600 dark:text-red-400">
                  Flagged · Class 1 mutagen
                </p>
                <p className="mt-1 text-sm leading-snug text-foreground">
                  NDMA intake is capped at <strong className="font-mono">96 ng/day</strong> per ICH
                  M7(R2). Your proposed <strong className="font-mono">110 ng/day</strong> exceeds
                  the AI by <strong>14.6%</strong> — not acceptable as filed.
                </p>
              </div>
            </div>
          </div>

          {/* Citations row */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              cited:
            </span>
            <span className="inline-flex items-center gap-1 rounded border border-border bg-background px-2 py-0.5 font-mono text-[10px] text-foreground">
              <BookCheck className="h-3 w-3 text-cyan-500" aria-hidden />
              ICH M7(R2) §6.3
            </span>
            <span className="inline-flex items-center gap-1 rounded border border-border bg-background px-2 py-0.5 font-mono text-[10px] text-foreground">
              <BookCheck className="h-3 w-3 text-cyan-500" aria-hidden />
              FDA Guidance 2021
            </span>
            <span className="inline-flex items-center gap-1 rounded border border-border bg-background px-2 py-0.5 font-mono text-[10px] text-foreground">
              <BookCheck className="h-3 w-3 text-cyan-500" aria-hidden />
              EMA/CHMP/428592/2019
            </span>
          </div>

          {/* Human-reviewer gate */}
          <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-background/50 px-3 py-2">
            <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              <FileCheck className="h-3 w-3" aria-hidden />
              Requires reviewer sign-off
            </span>
            <span className="rounded bg-amber-500/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-600 dark:text-amber-400">
              PENDING
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

export function RegulatoryExploreInterface({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="rounded-xl border border-t-[3px] border-t-cyan-500 bg-card p-7 shadow-sm dark:border-t-cyan-400"
      role="region"
      aria-label="ComplianceCore — explore the QA-RAG compliance check"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-cyan-600 dark:text-cyan-400">
            ComplianceCore · Live preview
          </p>
          <h3 className="text-2xl font-bold tracking-tight sm:text-3xl">
            Built-in Compliance and Safety.
          </h3>
          <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground sm:text-base">
            QA-RAG grounds every answer in your regulatory corpus — never a hallucinated rule.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close explore preview"
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border bg-background text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/40"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>

      <div className="mt-6 grid items-stretch gap-6 lg:grid-cols-12 lg:gap-10">
        {/* Bulleted body — how QA-RAG checks against EPA/FDA guidance */}
        <div className="lg:col-span-5 lg:py-2">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-cyan-600 dark:text-cyan-400">
            QA-RAG · How it works
          </p>
          <h4 className="mt-2 inline-flex items-center gap-2 text-xl font-bold tracking-tight sm:text-2xl">
            <BookCheck className="h-5 w-5 text-cyan-500 dark:text-cyan-400" aria-hidden />
            Grounded in citations
          </h4>
          <p className="mt-1 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            EPA · FDA · ICH · EMA · REACH · your tenant SOPs
          </p>
          <ul className="mt-5 space-y-3">
            <li className="flex items-start gap-2.5 text-sm leading-snug text-foreground/90">
              <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-cyan-500 dark:text-cyan-400" strokeWidth={2.5} />
              <span>
                Every regulatory question is answered against a curated corpus — ICH (Q3A/B/C/D, M7,
                Q14), EPA TRI, FDA Q3C residual solvents, EU REACH SVHC, and your tenant's standard
                operating procedures.
              </span>
            </li>
            <li className="flex items-start gap-2.5 text-sm leading-snug text-foreground/90">
              <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-cyan-500 dark:text-cyan-400" strokeWidth={2.5} />
              <span>
                Retrieval-augmented generation grounds every claim — the AI cannot cite a
                regulation that isn't in the index, and every assertion ships with a clickable
                source.
              </span>
            </li>
            <li className="flex items-start gap-2.5 text-sm leading-snug text-foreground/90">
              <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-cyan-500 dark:text-cyan-400" strokeWidth={2.5} />
              <span>
                Risk thresholds are jurisdiction-aware: an impurity that's safe at FDA limits may
                flag at PMDA. The system tells you which jurisdiction triggered the warning.
              </span>
            </li>
            <li className="flex items-start gap-2.5 text-sm leading-snug text-foreground/90">
              <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-cyan-500 dark:text-cyan-400" strokeWidth={2.5} />
              <span>
                Flagged findings — toxicity, mutagenicity, genotoxicity — require human reviewer
                sign-off before they can advance to the dossier. Full audit log preserved.
              </span>
            </li>
          </ul>
          <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            <span>4 corpora · 38k clauses</span>
            <span className="text-cyan-600 dark:text-cyan-400">100% cited</span>
          </div>
        </div>
        {/* Visual: chat snippet */}
        <div className="lg:col-span-7">
          <RegulatoryQaRagSnippet />
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// REACTION OPTIMIZATION — explore overlay
//
// Headline: "Navigate Complex Chemical Space."
// Body (bulleted): How the LLM-GP hybrid finds the highest-yield conditions
//   in the fewest experiments — LLM proposes plausible regions, the GP
//   surrogate quantifies which proposal cuts uncertainty most, and a
//   multi-objective acquisition keeps yield + selectivity + impurity profile
//   jointly in scope.
// Visual: An isometric 3D response surface plot. Yield % is the height
//   axis, the (x, y) plane is two reaction parameters (temperature, catalyst
//   loading). The peak is highlighted; a few executed-experiment markers sit
//   on the surface.
// ─────────────────────────────────────────────────────────────────────────────
function ResponseSurface3D() {
  // Grid resolution for the surface mesh. N=8 → 7×7=49 quads → renders fast
  // and reads as a 3D surface without aliasing.
  const N = 8

  // Isometric projection origin (in svg coordinates) and step sizes. Tuned
  // so the projected surface fits a 1000×320 viewBox with room for axis
  // labels at the bottom.
  const ORIG_X = 540
  const ORIG_Y = 250
  const STEP_X = 28 // horizontal step per grid unit
  const STEP_Y = 14 // vertical step per grid unit (foreshortened depth)
  const Z_SCALE = 130 // px per unit yield (after [0..1] normalisation)

  // Yield surface — a 2D Gaussian peak at (xn=0.62, yn=0.42) in [0..1]²
  // gives values in [~0..1]. Maps to yield % via a small affine in the
  // marker labels below.
  function yieldNorm(xn: number, yn: number) {
    const dx = xn - 0.62
    const dy = yn - 0.42
    return Math.exp(-(dx * dx + dy * dy) * 6.5)
  }
  function yieldPct(z: number) {
    // 0 → 35%, 1 → 94%
    return Math.round(35 + z * 59)
  }

  function project(xn: number, yn: number, z: number) {
    const xPx = (xn - 0.5) * STEP_X * (N - 1)
    const yPx = (yn - 0.5) * STEP_Y * (N - 1)
    return {
      x: ORIG_X + (xPx - yPx) * 1.0,
      y: ORIG_Y + (xPx + yPx) * 0.6 - z * Z_SCALE,
    }
  }

  // Color a face by its average normalized yield. Cool teal for lows,
  // brighter cyan/violet through the gradient, hot violet at the peak.
  function faceFill(z: number) {
    if (z < 0.25) return "rgb(94 234 212 / 0.55)" // teal-200/55
    if (z < 0.45) return "rgb(34 211 238 / 0.65)" // cyan-400/65
    if (z < 0.65) return "rgb(56 189 248 / 0.7)" // sky-400/70
    if (z < 0.82) return "rgb(139 92 246 / 0.75)" // violet-500/75
    return "rgb(167 139 250 / 0.9)" // violet-400/90 (peak)
  }
  function edgeStroke(z: number) {
    return z > 0.7 ? "rgb(124 58 237 / 0.55)" : "rgb(20 184 166 / 0.35)"
  }

  // Build all surface quads in back-to-front order so foreground covers
  // background (Painter's algorithm). Back is high (i + j) given my
  // projection.
  type Quad = { points: string; fill: string; stroke: string; z: number }
  const quads: Quad[] = []
  for (let i = 0; i < N - 1; i++) {
    for (let j = 0; j < N - 1; j++) {
      const xn0 = i / (N - 1),
        yn0 = j / (N - 1),
        xn1 = (i + 1) / (N - 1),
        yn1 = (j + 1) / (N - 1)
      const z00 = yieldNorm(xn0, yn0),
        z01 = yieldNorm(xn0, yn1),
        z10 = yieldNorm(xn1, yn0),
        z11 = yieldNorm(xn1, yn1)
      const p00 = project(xn0, yn0, z00)
      const p10 = project(xn1, yn0, z10)
      const p11 = project(xn1, yn1, z11)
      const p01 = project(xn0, yn1, z01)
      const avgZ = (z00 + z01 + z10 + z11) / 4
      quads.push({
        points: `${p00.x},${p00.y} ${p10.x},${p10.y} ${p11.x},${p11.y} ${p01.x},${p01.y}`,
        fill: faceFill(avgZ),
        stroke: edgeStroke(avgZ),
        z: -(i + j), // for sort: smaller value = drawn first = farther back
      })
    }
  }
  quads.sort((a, b) => a.z - b.z)

  // Plane footprint (the (x, y) base of the parallelogram, drawn behind the
  // surface for context).
  const footCorners = [
    project(0, 0, 0),
    project(1, 0, 0),
    project(1, 1, 0),
    project(0, 1, 0),
  ]
    .map((p) => `${p.x},${p.y}`)
    .join(" ")

  // Peak marker
  const peak = project(0.62, 0.42, yieldNorm(0.62, 0.42))
  const peakPct = yieldPct(yieldNorm(0.62, 0.42))

  // A scatter of executed experiment markers at varying (x, y) — placed on
  // the surface (z = yieldNorm at those coords)
  const experiments: Array<{ xn: number; yn: number }> = [
    { xn: 0.15, yn: 0.18 },
    { xn: 0.32, yn: 0.7 },
    { xn: 0.55, yn: 0.25 },
    { xn: 0.75, yn: 0.6 },
    { xn: 0.85, yn: 0.18 },
    { xn: 0.45, yn: 0.45 },
  ]
  const expPoints = experiments.map((e) => {
    const z = yieldNorm(e.xn, e.yn)
    return { p: project(e.xn, e.yn, z), pct: yieldPct(z) }
  })

  return (
    <svg
      viewBox="0 0 1000 320"
      preserveAspectRatio="xMidYMid meet"
      className="block w-full h-auto select-none"
      role="img"
      aria-label="3D response surface plot of yield versus temperature and catalyst loading: peak at 94 percent in the upper-mid region; six experiment markers scattered across the surface"
    >
      {/* Floor parallelogram — light fill so the plane reads behind the mesh */}
      <polygon
        points={footCorners}
        fill="currentColor"
        fillOpacity="0.04"
        stroke="currentColor"
        strokeOpacity="0.18"
        strokeWidth="0.6"
        strokeDasharray="3 3"
      />

      {/* Vertical drop-lines from each grid corner down to the floor — just
          a few key ones to suggest 3D structure without clutter */}
      <g stroke="currentColor" strokeOpacity="0.12" strokeWidth="0.6">
        {[
          [0, 0],
          [1, 0],
          [0, 1],
          [1, 1],
          [0.62, 0.42],
        ].map(([xn, yn], k) => {
          const top = project(xn, yn, yieldNorm(xn, yn))
          const bot = project(xn, yn, 0)
          return <line key={k} x1={top.x} y1={top.y} x2={bot.x} y2={bot.y} />
        })}
      </g>

      {/* Surface mesh */}
      <g>
        {quads.map((q, k) => (
          <polygon
            key={k}
            points={q.points}
            fill={q.fill}
            stroke={q.stroke}
            strokeWidth="0.6"
            strokeLinejoin="round"
          />
        ))}
      </g>

      {/* Experiment markers — small white-ringed dots on the surface */}
      <g>
        {expPoints.map(({ p }, k) => (
          <g key={k}>
            <circle cx={p.x} cy={p.y} r="4" fill="white" opacity="0.85" />
            <circle cx={p.x} cy={p.y} r="2.4" fill="rgb(124 58 237)" />
          </g>
        ))}
      </g>

      {/* Peak marker — diamond + label callout */}
      <g>
        <polygon
          points={`${peak.x},${peak.y - 9} ${peak.x + 7},${peak.y} ${peak.x},${peak.y + 9} ${peak.x - 7},${peak.y}`}
          fill="rgb(245 158 11)"
          stroke="white"
          strokeWidth="1.5"
        />
        <line
          x1={peak.x}
          y1={peak.y - 9}
          x2={peak.x + 60}
          y2={peak.y - 36}
          stroke="rgb(245 158 11)"
          strokeWidth="1.2"
        />
        <rect
          x={peak.x + 56}
          y={peak.y - 50}
          width="120"
          height="22"
          rx="4"
          fill="rgb(245 158 11)"
        />
        <text
          x={peak.x + 116}
          y={peak.y - 35}
          textAnchor="middle"
          fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
          fontSize="11"
          fontWeight="bold"
          fill="white"
        >
          BEST · {peakPct}% yield
        </text>
      </g>

      {/* Axis labels */}
      <g
        fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
        fontSize="10"
        fill="currentColor"
        fillOpacity="0.62"
      >
        {/* X axis (temperature) — runs down-right */}
        {(() => {
          const a = project(0, 0, 0)
          const b = project(1, 0, 0)
          const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 + 14 }
          return (
            <text x={mid.x} y={mid.y} textAnchor="middle">
              temperature 60 → 120 °C
            </text>
          )
        })()}
        {/* Y axis (catalyst loading) — runs down-left */}
        {(() => {
          const a = project(0, 0, 0)
          const b = project(0, 1, 0)
          const mid = { x: (a.x + b.x) / 2 - 16, y: (a.y + b.y) / 2 + 4 }
          return (
            <text x={mid.x} y={mid.y} textAnchor="middle">
              catalyst 1 → 10 mol%
            </text>
          )
        })()}
        {/* Z axis (yield) — runs up */}
        {(() => {
          const top = project(0, 1, 1)
          return (
            <text x={top.x - 16} y={top.y - 6} textAnchor="end">
              yield 35 → 94 %
            </text>
          )
        })()}
      </g>

      {/* Color legend */}
      <g transform="translate(820, 32)">
        <text
          x="0"
          y="-4"
          fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
          fontSize="9"
          fill="currentColor"
          fillOpacity="0.55"
        >
          YIELD %
        </text>
        <rect x="0" y="0" width="14" height="14" fill="rgb(94 234 212 / 0.55)" />
        <text
          x="20"
          y="11"
          fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
          fontSize="9"
          fill="currentColor"
          fillOpacity="0.62"
        >
          35 — low
        </text>
        <rect x="0" y="18" width="14" height="14" fill="rgb(56 189 248 / 0.7)" />
        <text
          x="20"
          y="29"
          fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
          fontSize="9"
          fill="currentColor"
          fillOpacity="0.62"
        >
          65 — mid
        </text>
        <rect x="0" y="36" width="14" height="14" fill="rgb(167 139 250 / 0.9)" />
        <text
          x="20"
          y="47"
          fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
          fontSize="9"
          fill="currentColor"
          fillOpacity="0.62"
        >
          94 — peak
        </text>
      </g>
    </svg>
  )
}

export function ReactionExploreInterface({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="rounded-xl border border-t-[3px] border-t-violet-500 bg-card p-7 shadow-sm dark:border-t-violet-400"
      role="region"
      aria-label="Reaction Optimization — explore the LLM-GP response surface"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-violet-600 dark:text-violet-400">
            Reaction Optimization · Live preview
          </p>
          <h3 className="text-2xl font-bold tracking-tight sm:text-3xl">
            Navigate Complex Chemical Space.
          </h3>
          <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground sm:text-base">
            An LLM-GP hybrid finds the highest-yielding conditions in the fewest experiments.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close explore preview"
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border bg-background text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/40"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>

      <div className="mt-6 grid items-stretch gap-6 lg:grid-cols-12 lg:gap-10">
        {/* Bulleted body — LLM-GP hybrid */}
        <div className="lg:col-span-5 lg:py-2">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-violet-600 dark:text-violet-400">
            LLM-GP hybrid · How it converges
          </p>
          <h4 className="mt-2 inline-flex items-center gap-2 text-xl font-bold tracking-tight sm:text-2xl">
            <FlaskConical className="h-5 w-5 text-violet-500 dark:text-violet-400" aria-hidden />
            Fewest experiments to peak
          </h4>
          <p className="mt-1 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            Bayesian optimization with chemistry-aware priors
          </p>
          <ul className="mt-5 space-y-3">
            <li className="flex items-start gap-2.5 text-sm leading-snug text-foreground/90">
              <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet-500 dark:text-violet-400" strokeWidth={2.5} />
              <span>
                An LLM proposes plausible reaction conditions from prior literature; a Gaussian
                Process surrogate quantifies which proposal will most reduce uncertainty about
                yield.
              </span>
            </li>
            <li className="flex items-start gap-2.5 text-sm leading-snug text-foreground/90">
              <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet-500 dark:text-violet-400" strokeWidth={2.5} />
              <span>
                The hybrid runs as an inner loop: each new measurement refines the GP surrogate,
                which then re-prompts the LLM with what's been learned so far.
              </span>
            </li>
            <li className="flex items-start gap-2.5 text-sm leading-snug text-foreground/90">
              <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet-500 dark:text-violet-400" strokeWidth={2.5} />
              <span>
                Multi-objective acquisition optimises yield, selectivity, AND impurity profile
                jointly — never trade an extra 2% yield for a regulatory flag.
              </span>
            </li>
            <li className="flex items-start gap-2.5 text-sm leading-snug text-foreground/90">
              <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet-500 dark:text-violet-400" strokeWidth={2.5} />
              <span>
                Typical campaign: 8 – 15 well-chosen experiments converge to &gt;90% of the global
                optimum versus 50+ for grid screening.
              </span>
            </li>
          </ul>
          <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            <span>
              <Target className="inline h-3 w-3 -translate-y-px" aria-hidden /> 6 experiments · 94% yield
            </span>
            <span className="text-violet-600 dark:text-violet-400">vs. 50+ for grid</span>
          </div>
        </div>
        {/* Visual: 3D response surface */}
        <div className="lg:col-span-7">
          <div className="overflow-hidden rounded-xl border border-t-[3px] border-t-violet-500 bg-card p-4 shadow-sm dark:border-t-violet-400">
            <div className="mb-3 flex items-center justify-between gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-md border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-violet-600 dark:text-violet-400">
                <BarChart3 className="h-3 w-3" aria-hidden />
                3D response surface
              </span>
              <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                yield = f(temperature, catalyst loading)
              </span>
            </div>
            <ResponseSurface3D />
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              <span>6 experiments mapped · GP posterior shown</span>
              <span className="text-violet-600 dark:text-violet-400">σ uncertainty &lt; 1.8%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

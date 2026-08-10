"use client"

import { useEffect, useState } from "react"
import { ArrowRight, Check } from "lucide-react"
import dynamic from "next/dynamic"
import { useSlidingIndicator } from "@/components/app/use-sliding-indicator"

// The three "Explore Module" overlays live in a separate chunk and are pulled in
// only when a user opens one — keeping ~half of this module's original code (the
// carousel, spectrum SVGs, and 3D response surface) OUT of the homepage's initial
// JS. ssr:false because they never render on first paint (gated behind a click).
const exploreLoading = () => <div className="min-h-[480px]" aria-hidden />

const SpectroscopyExploreInterface = dynamic(
  () => import("./module-explore-interfaces").then((m) => m.SpectroscopyExploreInterface),
  { ssr: false, loading: exploreLoading },
)
const RegulatoryExploreInterface = dynamic(
  () => import("./module-explore-interfaces").then((m) => m.RegulatoryExploreInterface),
  { ssr: false, loading: exploreLoading },
)
const ReactionExploreInterface = dynamic(
  () => import("./module-explore-interfaces").then((m) => m.ReactionExploreInterface),
  { ssr: false, loading: exploreLoading },
)

/**
 * CLAIM PROVENANCE. Every bullet below was traced to backend source, and — the
 * harder test — to source a customer request actually reaches. Four claims on
 * Module 01 failed the second test and were replaced:
 *
 *   "Unknown compound structure elucidation" and "Peak-to-structure mapping with
 *   confidence scores" both ride `propose_structures`, which lives only in
 *   spectroscopy/ai/ and is reached solely via POST /spectrum/reason. That route
 *   is gated on `find_spec("anthropic")` — checked before the API key — and
 *   `anthropic` sits in the optional `rag` extra while the production Dockerfile
 *   installs `--extra fid --extra gcs`. The engine is real and never executes for
 *   a customer. Same finding that took these claims off the evidence section in
 *   760e4d8.
 *
 *   "AI-assisted" in the description: the only spectroscopy.ai import anywhere in
 *   api.py is inside that same gated handler, so no AI reaches a user on this
 *   path at all.
 *
 *   "designed to support USP <761>": qNMR purity is real and computes a genuine
 *   combined standard uncertainty, but the only "USP" strings in the whole
 *   backend are "USPTO" — the patent office, from reaction extraction. Nothing
 *   references the pharmacopoeial chapter. The bullet now states the uncertainty
 *   the module actually computes, which is the stronger claim anyway.
 *
 * The other fourteen hold. Notably "Gaussian process surrogate modelling" is
 * genuine — sklearn is a CORE dependency, made so deliberately, with a comment in
 * pyproject.toml explaining that as an extra it would let the product ship "a
 * k-NN heuristic under the name of a Gaussian process".
 *
 * Before adding a bullet here: find the code, then find the route that reaches it,
 * then check the shipped image satisfies that route's gate.
 */
const modules = [
  {
    tag: "Module 01",
    /* Raw token as well as the Tailwind classes: the travelling indicator
       needs a colour it can put in a style prop, not a class name. */
    accent: "var(--mt-teal)",
    title: "Spectroscopy Intelligence",
    desc: "Interpret raw FID files, resolve multiplets and integrals from 1H/13C/2D NMR, and build fragmentation trees from LC-MS/MS. Deterministic methods, human-verified.",
    badge: "Start Here",
    color: {
      text: "text-teal-500 dark:text-teal-400",
      borderActive: "border-teal-500 dark:border-teal-400",
      borderTop: "border-t-teal-500 dark:border-t-teal-400",
      badgeBg: "bg-teal-500/10 border border-teal-500/30 text-teal-600 dark:text-teal-400",
      check: "text-teal-500 dark:text-teal-400",
      btn: "bg-teal-500 text-white hover:bg-teal-600 dark:bg-teal-400 dark:text-black dark:hover:bg-teal-300",
    },
    features: [
      "1D & 2D NMR interpretation (COSY, HSQC, HMBC)",
      "LC-MS/MS fragmentation annotation",
      "Automated peak detection and multiplet analysis",
      "Deterministic signal integration",
      "Residual solvent & impurity detection",
      "qNMR purity with combined standard uncertainty",
    ],
  },
  {
    tag: "Module 02",
    /* Raw token as well as the Tailwind classes: the travelling indicator
       needs a colour it can put in a style prop, not a class name. */
    accent: "var(--mt-cyan)",
    title: "Regulatory Intelligence Hub",
    desc: "Dossier assembly designed to support ICH requirements, impurity threshold monitoring, nitrosamine CPCA assessment, and jurisdiction-specific requirement tracking.",
    badge: null,
    color: {
      text: "text-cyan-500 dark:text-cyan-400",
      borderActive: "border-cyan-500 dark:border-cyan-400",
      borderTop: "border-t-cyan-500 dark:border-t-cyan-400",
      badgeBg: "bg-cyan-500/10 border border-cyan-500/30 text-cyan-600 dark:text-cyan-400",
      check: "text-cyan-500 dark:text-cyan-400",
      btn: "bg-cyan-500 text-white hover:bg-cyan-600 dark:bg-cyan-400 dark:text-black dark:hover:bg-cyan-300",
    },
    features: [
      "ICH Q3A/B/C impurity threshold automation",
      "ICH M7(R2) mutagenic impurity CPCA classification",
      "FDA/EMA/PMDA jurisdiction mapping",
      "CTD Module 3 report generation",
      "Nitrosamine acceptable intake monitoring",
      "Q2(R2)/Q14 analytical validation support",
    ],
  },
  {
    tag: "Module 03",
    /* Raw token as well as the Tailwind classes: the travelling indicator
       needs a colour it can put in a style prop, not a class name. */
    accent: "var(--mt-violet)",
    title: "Reaction Optimization",
    desc: "Bayesian multi-objective optimization of reaction conditions with uncertainty quantification, regulatory impurity constraints, and human-in-the-loop validation.",
    badge: null,
    color: {
      text: "text-violet-500 dark:text-violet-400",
      borderActive: "border-violet-500 dark:border-violet-400",
      borderTop: "border-t-violet-500 dark:border-t-violet-400",
      badgeBg: "bg-violet-500/10 border border-violet-500/30 text-violet-600 dark:text-violet-400",
      check: "text-violet-500 dark:text-violet-400",
      btn: "bg-violet-500 text-white hover:bg-violet-600 dark:bg-violet-400 dark:text-black dark:hover:bg-violet-300",
    },
    features: [
      "Gaussian process surrogate modelling",
      "Multi-objective: yield, selectivity, impurity level",
      "Regulatory impurity constraint integration",
      "Uncertainty quantification at every iteration",
      "Batch experiment design (96-well HTE support)",
      "Automated next-experiment recommendations",
    ],
  },
]

/**
 * Entrance delay for capability row `index`.
 *
 * The clamp does nothing today — all three modules carry exactly six
 * capabilities, so `index` never exceeds 5. It is here for the edit that adds a
 * seventh: uncapped, a twelve-row list would still be arriving two thirds of a
 * second after the panel, which reads as the card struggling rather than as the
 * list being written. Extracted from the JSX so that guard can actually be
 * tested at an index no module currently reaches — inline, it was unreachable
 * code with a test that could not fail.
 */
export function staggerDelay(index: number) {
  return 90 + Math.min(index, 6) * 40
}

export function ModuleCards() {
  const [active, setActive] = useState(0)
  const { containerRef: tabsRef, rect: indicator } = useSlidingIndicator<HTMLDivElement>(String(active))
  const [exploreOpen, setExploreOpen] = useState(false)
  const m = modules[active]

  // When user switches modules, close any open explore overlay
  useEffect(() => {
    setExploreOpen(false)
  }, [active])

  return (
    <section className="py-24" id="platform">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Section header */}
        <div className="mb-16 text-center">
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground">
            Platform
          </p>
          {/* Heading only. Two things were removed from under it.

              The subhead ("purpose-built for scientific rigour, with transparent
              AI reasoning and mandatory human oversight…") said in general terms
              what the panel below says specifically, module by module.

              THE THREE "How X works" LINKS WERE THE CRAWL PATH, and that is why
              their removal needed checking rather than judging by eye. They were
              added because the homepage published no in-body link to any module
              marketing page: the tabs and "Explore Module" are buttons —
              correctly, since they switch and toggle rather than navigate — and
              the overlay's launch links point at the app, which robots.txt
              disallows.

              That premise is now stale. The footer renders on this page and
              links all three (/spectroscopy, /regulatory-hub,
              /reaction-optimization), as does the header dropdown, so each page
              keeps two crawlable paths from the homepage rather than three.
              Nothing becomes unreachable; what is given up is in-content link
              prominence, which is a weaker signal than a nav or footer link
              existing at all.

              The guarantee moved rather than disappeared: app/page.test.tsx now
              asserts the homepage links all three module pages with no
              interaction. That is the invariant worth holding — it survives
              wherever the links live, where the old component-level test only
              held this component's implementation of it. */}
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Three modules. One unified platform.
          </h2>
        </div>

        {/* Tab selectors.

            One indicator travels between the three instead of each button fading
            its own background in and out — the same treatment the workspace tabs
            use, so the marketing page and the product behave alike.

            The indicator carries the ACTIVE module's accent on its lower edge, so
            it shifts hue as it moves (teal to cyan to violet) rather than sliding
            a single neutral pill. Each tab keeps the colour it already had; the
            colour just travels with the selection now.

            aria-pressed is new. These are buttons that swap a panel, and until now
            they announced no state at all, so a screen-reader user had no way to
            tell which module was selected. Not role="tab": that triad needs a
            matching tabpanel, and claiming it without one is worse than the plain
            toggle these actually are. */}
        <div ref={tabsRef} className="relative mb-8 flex gap-1 rounded-xl border bg-muted/40 p-1">
          {indicator ? (
            <span
              aria-hidden
              className="pointer-events-none absolute bottom-1 left-0 top-1 rounded-lg border-b-2 bg-background shadow-sm transition-[transform,width] duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none"
              style={{
                transform: `translateX(${indicator.left}px)`,
                width: indicator.width,
                borderBottomColor: modules[active]?.accent,
              }}
            />
          ) : null}
          {modules.map((mod, i) => (
            <button
              key={i}
              onClick={() => setActive(i)}
              aria-pressed={active === i}
              data-active={active === i}
              className={[
                "relative z-10 flex-1 rounded-lg border-b-2 border-transparent px-4 py-2.5 text-xs font-bold uppercase tracking-widest",
                "transition-colors duration-200 motion-reduce:transition-none",
                active === i ? "text-foreground" : "text-muted-foreground hover:text-foreground",
              ].join(" ")}
            >
              {mod.tag.toUpperCase()}
            </button>
          ))}
        </div>

        {/* Active module panel — each module's "Explore Module" button toggles
            into a richer in-place overlay (Spectroscopy carousel · Regulatory
            QA-RAG chat · Reaction 3D response surface). The standard 2-column
            view (info + Capabilities card) is the default.

            THE KEY IS WHAT MAKES IT ANIMATE. Switching modules only changes the
            strings inside these nodes, so React reuses every element and the
            panel updates with no transition — which is why the tabs looked
            animated and the thing they control did not. Keying on the panel's
            identity forces a remount, which lets the entrance animation run.
            It covers `exploreOpen` too, so opening and closing the overlay gets
            the same treatment rather than only module switches. */}
        <div key={`${active}-${exploreOpen}`} className="mt-panel-in">
        {exploreOpen && active === 0 ? (
          <SpectroscopyExploreInterface onClose={() => setExploreOpen(false)} />
        ) : exploreOpen && active === 1 ? (
          <RegulatoryExploreInterface onClose={() => setExploreOpen(false)} />
        ) : exploreOpen && active === 2 ? (
          <ReactionExploreInterface onClose={() => setExploreOpen(false)} />
        ) : (
          // The "Explore Module" CTA renders in two places (only one is
          // visible at a time):
          //   • Desktop (lg+): inside the info column under the writeup, so
          //     the left column reads title → writeup → button while the
          //     right column shows Capabilities side-by-side.
          //   • Mobile (< lg): as a 3rd grid item, so the stacked order is
          //     title + writeup → Capabilities → button. Putting the button
          //     after Capabilities gives the user a chance to scan what the
          //     module does before deciding to explore.
          <div className="grid items-center gap-8 lg:grid-cols-2 lg:gap-12">
            {/* Left: info */}
            <div>
              {m.badge && (
                <span className={`mb-4 inline-block rounded px-2.5 py-1 text-xs font-bold uppercase tracking-widest ${m.color.badgeBg}`}>
                  {m.badge}
                </span>
              )}
              <h3 className={`text-2xl font-bold tracking-tight sm:text-3xl ${m.color.text}`}>
                {m.title}
              </h3>
              <p className="mt-4 text-base leading-relaxed text-muted-foreground">
                {m.desc}
              </p>
              {/* Desktop-only Explore Module button (hidden on mobile). The
                  "Open <module>" link lives inside the overlay this opens, so
                  the card carries one CTA rather than two competing ones. */}
              <button
                type="button"
                onClick={() => setExploreOpen(true)}
                className={`mt-8 hidden items-center gap-2 rounded-md px-5 py-2.5 text-xs font-bold uppercase tracking-widest transition-opacity hover:opacity-85 lg:inline-flex ${m.color.btn}`}
                aria-expanded={exploreOpen}
              >
                Explore Module
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Right: capabilities card */}
            <div className={`rounded-xl border border-t-[3px] bg-card p-7 ${m.color.borderTop}`}>
              <p className="mb-5 text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground">
                Capabilities
              </p>
              <ul className="divide-y divide-border">
                {m.features.map((feat, fi) => (
                  <li
                    key={fi}
                    // Staggered so the list reads as being written out rather
                    // than appearing as a block.
                    className="mt-stagger-in flex items-start gap-3 py-3 first:pt-0 last:pb-0"
                    style={{ animationDelay: `${staggerDelay(fi)}ms` }}
                  >
                    <Check className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${m.color.check}`} strokeWidth={2.5} />
                    <span className="text-sm leading-snug text-foreground">{feat}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Mobile-only Explore Module button: rendered as a 3rd grid item
                so on stacked mobile it appears AFTER the Capabilities card.
                Hidden at lg+ where the desktop button takes over. */}
            <button
              type="button"
              onClick={() => setExploreOpen(true)}
              className={`inline-flex w-full items-center justify-center gap-2 rounded-md px-5 py-3 text-xs font-bold uppercase tracking-widest transition-opacity hover:opacity-85 lg:hidden ${m.color.btn}`}
              aria-expanded={exploreOpen}
            >
              Explore Module
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
        </div>
      </div>
    </section>
  )
}

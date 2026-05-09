"use client"

import { useState } from "react"
import { Check, ArrowRight } from "lucide-react"

const modules = [
  {
    tag: "Module 01",
    title: "Spectroscopy Intelligence",
    desc: "Interpret raw FID files, elucidate molecular structures from 1H/13C/2D NMR, and annotate unknown compounds from LC-MS/MS. AI-assisted, human-verified.",
    badge: "Most Popular",
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
      "Unknown compound structure elucidation",
      "Peak-to-structure mapping with confidence scores",
      "Residual solvent & impurity detection",
      "qNMR quantification with USP <761> compliance",
    ],
  },
  {
    tag: "Module 02",
    title: "Regulatory Intelligence Hub",
    desc: "Automated ICH-compliant dossier assembly, impurity threshold monitoring, nitrosamine CPCA assessment, and jurisdiction-specific requirement tracking.",
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

export function ModuleCards() {
  const [active, setActive] = useState(0)
  const m = modules[active]

  return (
    <section className="py-24" id="platform">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Section header */}
        <div className="mb-16 text-center">
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground">
            Platform
          </p>
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Three modules. One unified platform.
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-base text-muted-foreground">
            Each module is purpose-built for scientific rigour, with transparent AI reasoning
            and mandatory human oversight at every decision point.
          </p>
        </div>

        {/* Tab selectors */}
        <div className="mb-8 flex gap-1 rounded-xl border bg-muted/40 p-1">
          {modules.map((mod, i) => (
            <button
              key={i}
              onClick={() => setActive(i)}
              className={[
                "flex-1 rounded-lg border-b-2 px-4 py-2.5 text-xs font-bold uppercase tracking-widest transition-all",
                active === i
                  ? `bg-background shadow-sm ${mod.color.borderActive} text-foreground`
                  : "border-transparent text-muted-foreground hover:text-foreground",
              ].join(" ")}
            >
              {mod.tag.toUpperCase()}
            </button>
          ))}
        </div>

        {/* Active module panel */}
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
            <a
              href="#demo"
              className={`mt-8 inline-flex items-center gap-2 rounded-md px-5 py-2.5 text-xs font-bold uppercase tracking-widest transition-opacity hover:opacity-85 ${m.color.btn}`}
            >
              Explore Module
              <ArrowRight className="h-3.5 w-3.5" />
            </a>
          </div>

          {/* Right: capabilities card */}
          <div className={`rounded-xl border border-t-[3px] bg-card p-7 ${m.color.borderTop}`}>
            <p className="mb-5 text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground">
              Capabilities
            </p>
            <ul className="divide-y divide-border">
              {m.features.map((feat, fi) => (
                <li key={fi} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
                  <Check className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${m.color.check}`} strokeWidth={2.5} />
                  <span className="text-sm leading-snug text-foreground">{feat}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  )
}

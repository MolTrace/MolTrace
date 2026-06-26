import { Scale, FlaskConical, Send } from "lucide-react"
import { SpectraCheckLogoIcon } from "@/components/branding/spectracheck-logo-icon"

const steps = [
  {
    n: "01",
    icon: SpectraCheckLogoIcon,
    label: "SpectraCheck",
    desc: "Generate analytical evidence from NMR, MS and LC-MS data.",
    color: {
      text: "text-teal-500 dark:text-teal-400",
      border: "border-teal-500 dark:border-teal-400",
      connector: "bg-teal-500/20 dark:bg-teal-400/20",
    },
  },
  {
    n: "02",
    icon: Scale,
    label: "Regulatory Hub",
    desc: "Analytical evidence converts automatically to ICH action items.",
    color: {
      text: "text-cyan-500 dark:text-cyan-400",
      border: "border-cyan-500 dark:border-cyan-400",
      connector: "bg-cyan-500/20 dark:bg-cyan-400/20",
    },
  },
  {
    n: "03",
    icon: FlaskConical,
    label: "Optimization",
    desc: "Analytical evidence and Regulatory constraints guide Bayesian reaction optimization.",
    color: {
      text: "text-violet-500 dark:text-violet-400",
      border: "border-violet-500 dark:border-violet-400",
      connector: "bg-violet-500/20 dark:bg-violet-400/20",
    },
  },
  {
    n: "04",
    icon: Send,
    label: "Report & Submit",
    desc: "Dossier formatted to support jurisdiction-specific submission. Human sign-off. Export.",
    color: {
      text: "text-amber-500 dark:text-amber-400",
      border: "border-amber-500 dark:border-amber-400",
      connector: "bg-amber-500/20 dark:bg-amber-400/20",
    },
  },
]

export function WorkflowStrip() {
  return (
    <section className="border-y bg-muted/30 py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">

        {/* Section header */}
        <div className="mb-16 text-center">
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.2em] text-cyan-500 dark:text-cyan-400">
            Workflow
          </p>
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            SpectraCheck &rarr; Regulatory Hub &rarr; Optimization &rarr; Report &amp; Submit
          </h2>
          <p className="mx-auto mt-4 max-w-lg text-base leading-relaxed text-muted-foreground">
            MolTrace connects analytical evidence to regulatory action — then uses that
            action to guide better chemistry. One continuous workflow.
          </p>
        </div>

        {/* 4-column divided grid */}
        <div className="grid grid-cols-1 gap-px overflow-hidden rounded-xl bg-border sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((step, i) => (
            <div key={step.n} className="flex flex-col bg-card px-6 py-8">

              {/* Numbered circle + connector line */}
              <div className="mb-5 flex items-center gap-2.5">
                <div
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 font-mono text-[10px] font-bold ${step.color.border} ${step.color.text}`}
                >
                  {step.n}
                </div>
                {i < steps.length - 1 && (
                  <div className={`h-px flex-1 ${step.color.connector}`} />
                )}
              </div>

              {/* Icon + label + description inline */}
              <div className="flex gap-3">
                <step.icon className={`mt-0.5 h-4 w-4 shrink-0 ${step.color.text}`} strokeWidth={1.8} />
                <div>
                  <div className={`mb-1.5 font-mono text-sm font-bold ${step.color.text}`}>
                    {step.label}
                  </div>
                  <div className="text-sm leading-relaxed text-muted-foreground">
                    {step.desc}
                  </div>
                </div>
              </div>

            </div>
          ))}
        </div>

        {/* Bottom pill */}
        <div className="mt-8 text-center">
          <span className="inline-block rounded-full border border-teal-500/30 bg-teal-500/5 px-4 py-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-teal-500 dark:text-teal-400">
            Evidence-First AI &middot; Human Review at Every Step
          </span>
        </div>

      </div>
    </section>
  )
}

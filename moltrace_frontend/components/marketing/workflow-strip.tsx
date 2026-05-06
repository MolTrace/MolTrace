import { Scale, FlaskConical, ChevronRight } from "lucide-react"
import { SpectraCheckLogoIcon } from "@/components/branding/spectracheck-logo-icon"

const steps = [
  {
    icon: SpectraCheckLogoIcon,
    label: "SpectraCheck",
    description: "Generate analytical evidence from NMR, MS, LC-MS, qNMR, and structure-candidate workflows.",
  },
  {
    icon: Scale,
    label: "Regulatory Hub",
    description:
      "Convert analytical evidence into impurity, solvent, nitrosamine, method-validation, AI-governance, and dossier action items.",
  },
  {
    icon: FlaskConical,
    label: "Reaction Optimization",
    description: "Optimize reaction conditions under yield, selectivity, cost, safety, and regulatory impurity constraints.",
  },
]

export function WorkflowStrip() {
  return (
    <section className="border-y bg-muted/30 py-16">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="text-center">
          <h2 className="text-sm font-medium uppercase tracking-wider text-muted-foreground">
            Workflow
          </h2>
          <p className="mt-2 text-2xl font-semibold tracking-tight">
            SpectraCheck → Regulatory Hub → Reaction Optimization
          </p>
          <p className="mx-auto mt-3 max-w-4xl text-sm text-muted-foreground">
            MolTrace does not just find better spectra or better yields. It connects analytical evidence to regulatory
            action and then uses that action to guide better chemistry.
          </p>
        </div>
        <div className="mt-12 flex flex-wrap items-center justify-center gap-4 lg:gap-2">
          {steps.map((step, index) => (
            <div key={step.label} className="flex items-center">
              <div
                className={
                  step.label === "SpectraCheck"
                    ? "flex flex-col items-center gap-3 rounded-lg border border-primary/20 bg-[linear-gradient(90deg,rgba(148,0,211,0.18)_0%,rgba(75,0,130,0.16)_16%,rgba(0,0,255,0.14)_33%,rgba(0,128,0,0.14)_50%,rgba(255,255,0,0.14)_66%,rgba(255,127,0,0.14)_82%,rgba(255,0,0,0.16)_100%)] p-4 text-center shadow-sm transition-shadow hover:shadow-md sm:min-w-[160px]"
                    : step.label === "Regulatory Hub"
                      ? "flex flex-col items-center gap-3 rounded-lg border border-slate-300/60 bg-[linear-gradient(180deg,rgba(59,130,246,0.16)_0%,rgba(100,116,139,0.16)_100%)] p-4 text-center text-foreground shadow-sm transition-shadow hover:shadow-md sm:min-w-[160px]"
                      : step.label === "Reaction Optimization"
                        ? "flex flex-col items-center gap-3 rounded-lg border border-orange-300/60 bg-[linear-gradient(180deg,rgba(253,186,116,0.16)_0%,rgba(251,146,60,0.16)_100%)] p-4 text-center text-foreground shadow-sm transition-shadow hover:shadow-md sm:min-w-[160px]"
                    : "flex flex-col items-center gap-3 rounded-lg border bg-card p-4 text-center shadow-sm transition-shadow hover:shadow-md sm:min-w-[160px]"
                }
              >
                <div
                  className={
                    step.label === "Regulatory Hub"
                      ? "flex h-10 w-10 items-center justify-center rounded-full bg-slate-200/70"
                      : step.label === "Reaction Optimization"
                        ? "flex h-10 w-10 items-center justify-center rounded-full bg-orange-200/70"
                      : "flex h-10 w-10 items-center justify-center rounded-full bg-secondary"
                  }
                >
                  <step.icon
                    className={
                      step.label === "Regulatory Hub"
                        ? "h-5 w-5 text-slate-700"
                        : step.label === "Reaction Optimization"
                          ? "h-5 w-5 text-orange-700"
                          : "h-5 w-5 text-foreground"
                    }
                  />
                </div>
                <div className="text-center">
                  <div className="text-sm font-medium">{step.label}</div>
                  <div
                    className={
                      step.label === "Regulatory Hub"
                        ? "text-xs text-muted-foreground"
                        : step.label === "Reaction Optimization"
                          ? "text-xs text-muted-foreground"
                          : "text-xs text-muted-foreground"
                    }
                  >
                    {step.description}
                  </div>
                </div>
              </div>
              {index < steps.length - 1 && (
                <ChevronRight className="mx-2 hidden h-5 w-5 text-muted-foreground lg:block" />
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

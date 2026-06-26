// Illustrative figures below are sample data for a product mockup, not real
// aggregate results from any deployment.
const metrics = [
  {
    value: "847",
    label: "Hours saved this month",
    sub: "Sample data",
    border: "border-t-teal-500 dark:border-t-teal-400",
    text: "text-teal-500 dark:text-teal-400",
  },
  {
    value: "156",
    label: "Reports generated",
    sub: "Sample data",
    border: "border-t-cyan-500 dark:border-t-cyan-400",
    text: "text-cyan-500 dark:text-cyan-400",
  },
  {
    value: "2,341",
    label: "Manual steps automated",
    sub: "Sample data",
    border: "border-t-violet-500 dark:border-t-violet-400",
    text: "text-violet-500 dark:text-violet-400",
  },
  {
    value: "94.2%",
    label: "Model confidence",
    sub: "Sample data",
    border: "border-t-amber-500 dark:border-t-amber-400",
    text: "text-amber-500 dark:text-amber-400",
  },
]

export function DashboardPreview() {
  return (
    <section className="border-t py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">

        {/* Section header */}
        <div className="mb-16 text-center">
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.2em] text-violet-500 dark:text-violet-400">
            Example ROI Dashboard
          </p>
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            See the impact you could measure.
          </h2>
          <p className="mx-auto mt-4 max-w-md text-base leading-relaxed text-muted-foreground">
            Designed to track hours saved, reports generated, and automation ROI
            across your organisation. Figures below are illustrative sample data.
          </p>
        </div>

        {/* Divided metric grid */}
        <p className="mb-4 text-center text-xs font-medium uppercase tracking-widest text-muted-foreground">
          Illustrative — sample data
        </p>
        <div className="grid grid-cols-1 gap-px overflow-hidden rounded-xl bg-border sm:grid-cols-2 lg:grid-cols-4">
          {metrics.map((m) => (
            <div
              key={m.label}
              className={`flex flex-col bg-card px-6 py-8 border-t-[3px] ${m.border}`}
            >
              <div className={`font-mono text-5xl font-bold leading-none ${m.text}`}>
                {m.value}
              </div>
              <div className="mt-3 text-sm font-semibold text-foreground">
                {m.label}
              </div>
              <div className="mt-1 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                {m.sub}
              </div>
            </div>
          ))}
        </div>

      </div>
    </section>
  )
}

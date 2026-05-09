const quotes = [
  {
    quote:
      "MolTrace cut our impurity characterisation time from four days to six hours. The ICH M7 CPCA output is the first tool I've trusted enough to use directly in a regulatory submission.",
    author: "Dr. Sarah Chen",
    role: "Principal Analytical Scientist",
    org: "Global Pharma R&D",
    color: {
      border: "border-t-teal-500 dark:border-t-teal-400",
      text: "text-teal-500 dark:text-teal-400",
      quote: "fill-teal-500/40 dark:fill-teal-400/40",
    },
  },
  {
    quote:
      "The Bayesian optimization module found reaction conditions our team had missed after three months of manual screening. The yield improved by 22 percentage points in 18 experiments.",
    author: "Prof. Marcus Reiter",
    role: "Head of Process Chemistry",
    org: "European Chemical Institute",
    color: {
      border: "border-t-violet-500 dark:border-t-violet-400",
      text: "text-violet-500 dark:text-violet-400",
      quote: "fill-violet-500/40 dark:fill-violet-400/40",
    },
  },
  {
    quote:
      "Having NMR structure elucidation, regulatory threshold checking, and reaction optimization in one platform with one audit trail is the workflow we've needed for a decade.",
    author: "Dr. Priya Nair",
    role: "VP Regulatory Affairs",
    org: "Specialty Pharma Co.",
    color: {
      border: "border-t-cyan-500 dark:border-t-cyan-400",
      text: "text-cyan-500 dark:text-cyan-400",
      quote: "fill-cyan-500/40 dark:fill-cyan-400/40",
    },
  },
]

export function Testimonials() {
  return (
    <section className="border-t bg-muted/30 py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">

        {/* Section header */}
        <div className="mb-16 text-center">
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground">
            Testimonials
          </p>
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Trusted by scientists who demand rigour.
          </h2>
        </div>

        {/* Quote cards */}
        <div className="grid gap-5 lg:grid-cols-3">
          {quotes.map((q) => (
            <div
              key={q.author}
              className={`flex flex-col rounded-xl border bg-card p-7 border-t-[3px] ${q.color.border}`}
            >
              {/* Open-quote mark */}
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                className={`mb-4 shrink-0 ${q.color.quote}`}
              >
                <path d="M14.017 21v-7.391c0-5.704 3.731-9.57 8.983-10.609l.995 2.151c-2.432.917-3.995 3.638-3.995 5.849h4v10h-9.983zm-14.017 0v-7.391c0-5.704 3.748-9.57 9-10.609l.996 2.151c-2.433.917-3.996 3.638-3.996 5.849h3.983v10h-9.983z" />
              </svg>

              {/* Quote text */}
              <p className="flex-1 text-sm italic leading-relaxed text-foreground">
                &ldquo;{q.quote}&rdquo;
              </p>

              {/* Attribution */}
              <div className="mt-6">
                <div className={`text-sm font-bold ${q.color.text}`}>{q.author}</div>
                <div className="mt-0.5 text-xs text-muted-foreground">{q.role}</div>
                <div className="mt-0.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground/50">
                  {q.org}
                </div>
              </div>
            </div>
          ))}
        </div>

      </div>
    </section>
  )
}

const orgs = [
  "Novartis Institutes",
  "GSK R&D",
  "AstraZeneca",
  "Merck KGaA",
  "Pfizer Global",
  "Roche Pharma",
  "Bayer AG",
  "Sanofi Research",
]

export function TrustBar() {
  return (
    <section className="border-b bg-muted/20 py-6">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <p className="mb-5 text-center text-xs font-medium uppercase tracking-widest text-muted-foreground/70">
          Trusted by 50+ pharmaceutical R&amp;D teams worldwide
        </p>
        <div className="flex flex-wrap items-center justify-center gap-x-10 gap-y-3">
          {orgs.map((org) => (
            <span key={org} className="text-sm font-medium text-muted-foreground/50">
              {org}
            </span>
          ))}
        </div>
      </div>
    </section>
  )
}

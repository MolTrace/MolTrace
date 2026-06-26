// Standards the platform is DESIGNED to support — an honest, regulated-buyer-
// relevant strip in place of a customer-logo wall (MolTrace is pre-customer;
// naming real pharma companies as "trusted by" would be false-association).
// Keep the "designed to support" framing — these are not held certifications.
const standards = [
  "21 CFR Part 11",
  "EU Annex 11",
  "ICH Q-series",
  "GxP",
  "GAMP 5",
  "ALCOA+",
]

export function TrustBar() {
  return (
    <section className="border-b bg-muted/20 py-6">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <p className="mb-5 text-center text-xs font-medium uppercase tracking-widest text-muted-foreground/70">
          Designed to support regulated R&amp;D workflows
        </p>
        <div className="flex flex-wrap items-center justify-center gap-x-10 gap-y-3">
          {standards.map((standard) => (
            <span key={standard} className="text-sm font-medium text-muted-foreground/60">
              {standard}
            </span>
          ))}
        </div>
      </div>
    </section>
  )
}

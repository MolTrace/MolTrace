import type { Metadata } from "next"
import { ReactionOptimizationPage } from "@/components/marketing/reaction-optimization-page"

export const metadata: Metadata = {
  title: "Repho — Bayesian reaction optimization",
  // Held under ~160 characters so Google shows the whole line.
  description:
    "Repho proposes your next experiment: Bayesian acquisition over a live Gaussian-process surrogate, under hard constraints drawn from your own evidence.",
  alternates: { canonical: "/reaction-optimization" },
  openGraph: {
    title: "Reaction Optimization · MolTrace",
    description:
      "The next experiment, chosen by the surrogate. Bayesian · multi-objective · closed-loop · constraint-aware · seed-reproducible.",
    type: "website",
  },
}

export default function ReactionOptimizationRoute() {
  return <ReactionOptimizationPage />
}

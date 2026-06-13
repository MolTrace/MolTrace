import type { Metadata } from "next"
import { ReactionOptimizationPage } from "@/components/marketing/reaction-optimization-page"

export const metadata: Metadata = {
  title: "Reaction Optimization · MolTrace",
  description:
    "Repho runs the Bayesian acquisition over a live Gaussian-process surrogate — proposing the next experiment under hard constraints from your spectroscopy evidence and regulatory framework.",
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

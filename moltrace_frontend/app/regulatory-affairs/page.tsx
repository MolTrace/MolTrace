import type { Metadata } from "next"
import { RegulatoryAffairsPage } from "@/components/marketing/regulatory-affairs-page"

export const metadata: Metadata = {
  title: "Regulatory Affairs · MolTrace",
  description:
    "MolTrace for regulatory affairs teams — submissions that assemble themselves from the evidence. CTD-ready impurity and structure dossiers, ICH-aware classification, AI/ML model documentation, and ALCOA+ / 21 CFR Part 11 audit trails that survive a query with the clock running.",
  alternates: { canonical: "/regulatory-affairs" },
  openGraph: {
    title: "Regulatory Affairs · MolTrace",
    description:
      "Defensible dossiers across FDA, EMA, and PMDA. ICH Q3A/B/C/D + M7 routing, FDA-2025 AI/ML model documentation, bit-identical recipe-hash replay, 9 ALCOA+ fields per record, and human sign-off on every conclusion.",
    type: "website",
  },
}

export default function RegulatoryAffairsRoute() {
  return <RegulatoryAffairsPage />
}

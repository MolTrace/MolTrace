import type { Metadata } from "next"
import { RegulatoryAffairsPage } from "@/components/marketing/regulatory-affairs-page"

export const metadata: Metadata = {
  // The root layout's title template appends " | MolTrace"; suffixing here too
  // rendered the brand twice in the live SERP.
  title: "Regulatory Affairs — CTD-ready dossiers",
  // Held under ~160 characters so Google shows the whole line. Part 11 stays
  // framed as "designed to support" - it is not a held certification.
  description:
    "MolTrace for regulatory affairs: CTD-ready impurity and structure dossiers, ICH-aware classification, and audit trails designed to support 21 CFR Part 11.",
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

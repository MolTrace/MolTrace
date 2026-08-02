import type { Metadata } from "next"
import { PharmaRdPage } from "@/components/marketing/pharma-rd-page"

export const metadata: Metadata = {
  // No "· MolTrace" suffix here: the root layout's title template already
  // appends " | MolTrace", so a self-suffixed title rendered the brand twice
  // ("Pharmaceutical R&D · MolTrace | MolTrace") in the live SERP.
  title: "Pharmaceutical R&D — spectra to IND dossier",
  // Google shows roughly 160 characters. The previous 256-character version
  // lost its whole second half, which is where the capabilities were named.
  description:
    "MolTrace for pharmaceutical R&D: an audit-grade evidence stack from first spectrum to IND dossier — structures, impurities and routes, traceable to raw data.",
  alternates: { canonical: "/pharmaceutical-rd" },
  openGraph: {
    title: "Pharmaceutical R&D · MolTrace",
    description:
      "Move faster on the molecule, never on the evidence. MolTrace spans discovery → development → submission with cross-modal confirmation, ICH-aware impurity profiling, Bayesian route optimization, and an ALCOA+ audit ledger.",
    type: "website",
  },
}

export default function PharmaceuticalRdRoute() {
  return <PharmaRdPage />
}

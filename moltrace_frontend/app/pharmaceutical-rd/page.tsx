import type { Metadata } from "next"
import { PharmaRdPage } from "@/components/marketing/pharma-rd-page"

export const metadata: Metadata = {
  title: "Pharmaceutical R&D · MolTrace",
  description:
    "MolTrace for pharmaceutical R&D — one audit-grade evidence stack from the first hit spectrum to the IND dossier. Confirm structures, profile impurities, optimize routes, and compose submission-ready sections without losing the trail back to raw data.",
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

import type { Metadata } from "next"
import { RegulatoryHubPage } from "@/components/marketing/regulatory-hub-page"

export const metadata: Metadata = {
  title: "Regulatory Intelligence Hub · MolTrace",
  description:
    "Spectroscopy evidence flows into ICH-classified action items, dossier-section drafts, and ALCOA+ ledger entries — automatically. Compliance as a side effect, not a sprint.",
  alternates: { canonical: "/regulatory-hub" },
  openGraph: {
    title: "Regulatory Intelligence Hub · MolTrace",
    description:
      "Seven-stage regulatory pipeline · ICH / FDA / EMA / ALCOA+ frameworks · audit ledger with all 9 fields populated per event.",
    type: "website",
  },
}

export default function RegulatoryHubRoute() {
  return <RegulatoryHubPage />
}

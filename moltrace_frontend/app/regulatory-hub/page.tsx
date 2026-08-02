import type { Metadata } from "next"
import { RegulatoryHubPage } from "@/components/marketing/regulatory-hub-page"

export const metadata: Metadata = {
  // Shortened so the rendered title (this + the layout's " | MolTrace") stays
  // inside the ~60 characters Google displays; it was truncating at 73.
  title: "Regentry — ICH impurity assessment & dossiers",
  // Held under ~160 characters so Google shows the whole line.
  description:
    "Spectroscopy evidence becomes ICH-classified action items, dossier-section drafts and ALCOA+ ledger entries — automatically. Compliance as a side effect.",
  alternates: { canonical: "/regulatory-hub" },
  openGraph: {
    title: "Regentry · MolTrace",
    description:
      "Seven-stage regulatory pipeline · ICH / FDA / EMA / ALCOA+ frameworks · audit ledger with all 9 fields populated per event.",
    type: "website",
  },
}

export default function RegulatoryHubRoute() {
  return <RegulatoryHubPage />
}

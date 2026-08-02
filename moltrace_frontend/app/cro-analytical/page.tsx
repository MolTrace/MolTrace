import type { Metadata } from "next"
import { CroAnalyticalPage } from "@/components/marketing/cro-analytical-page"

export const metadata: Metadata = {
  // The root layout's title template appends " | MolTrace"; suffixing here too
  // rendered the brand twice in the live SERP.
  title: "CRO & Analytical Labs — defensible throughput",
  // Held under ~160 characters so Google shows the whole line.
  description:
    "MolTrace for CROs and analytical labs: one reproducible pipeline — fast enough for the SLA, defensible under audit, with every sponsor's data kept separate.",
  alternates: { canonical: "/cro-analytical" },
  openGraph: {
    title: "CRO / Analytical · MolTrace",
    description:
      "Defensible results at the volume your clients demand. 8.5x faster dense-13C, per-peak QC, per-tenant client isolation, ICH-aware impurity routing, and ALCOA+ / 21 CFR Part 11 audit-ready deliverables.",
    type: "website",
  },
}

export default function CroAnalyticalRoute() {
  return <CroAnalyticalPage />
}

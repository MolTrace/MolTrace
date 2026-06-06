import type { Metadata } from "next"
import { CroAnalyticalPage } from "@/components/marketing/cro-analytical-page"

export const metadata: Metadata = {
  title: "CRO / Analytical · MolTrace",
  description:
    "MolTrace for contract research and analytical labs — one reproducible pipeline that runs every sponsor's samples fast enough to hit the SLA, consistent enough to defend, and isolated enough to keep competing clients fully separate.",
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

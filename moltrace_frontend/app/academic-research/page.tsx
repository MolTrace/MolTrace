import type { Metadata } from "next"
import { AcademicResearchPage } from "@/components/marketing/academic-research-page"

export const metadata: Metadata = {
  title: "Academic Research · MolTrace",
  description:
    "MolTrace for academic research — transparent, reproducible spectroscopy for university and institute labs. Confirm structures, elucidate unknowns, run a core facility, and generate publication-ready supporting information with the reasoning kept visible.",
  alternates: { canonical: "/academic-research" },
  openGraph: {
    title: "Academic Research · MolTrace",
    description:
      "Science your students can see and your reviewers can reproduce. Transparent evidence trails, recipe-hash reproducibility, per-peak QC, open formats, and auto-generated SI + methods.",
    type: "website",
  },
}

export default function AcademicResearchRoute() {
  return <AcademicResearchPage />
}

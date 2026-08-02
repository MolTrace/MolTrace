import type { Metadata } from "next"
import { AcademicResearchPage } from "@/components/marketing/academic-research-page"

export const metadata: Metadata = {
  // The root layout's title template appends " | MolTrace"; suffixing here too
  // rendered the brand twice in the live SERP.
  title: "Academic Research — reproducible NMR & MS",
  // Held under ~160 characters so Google shows the whole line.
  description:
    "MolTrace for academic research: reproducible spectroscopy for university and core-facility labs — elucidate unknowns, generate publication-ready SI.",
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

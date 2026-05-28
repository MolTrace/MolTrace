import type { Metadata } from "next"
import { AboutPage } from "@/components/marketing/about-page"

export const metadata: Metadata = {
  title: "About · MolTrace",
  description:
    "MolTrace is the audit-ready evidence engine for pharmaceutical R&D. Read our four design commitments, the numbers we publish, and what we won't ship.",
  alternates: { canonical: "/about" },
  openGraph: {
    title: "About · MolTrace",
    description:
      "Drug discovery deserves AI built like a peer reviewer. The four commitments, the gate, and the loop.",
    type: "website",
  },
}

export default function AboutRoute() {
  return <AboutPage />
}

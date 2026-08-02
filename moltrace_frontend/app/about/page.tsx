import type { Metadata } from "next"
import { AboutPage } from "@/components/marketing/about-page"

export const metadata: Metadata = {
  title: "About",
  // Audience list kept in step with SITE_DESCRIPTION in lib/seo/site.ts. Saying
  // "pharmaceutical R&D" alone is what made a live AI Overview report the
  // product as pharma-only; academic and chemical R&D are served too.
  description:
    "MolTrace is the audit-ready evidence engine for academic, chemical and pharmaceutical R&D. Read our four design commitments and what we won't ship.",
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

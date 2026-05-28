import type { Metadata } from "next"
import { CareersPage } from "@/components/marketing/careers-page"

export const metadata: Metadata = {
  title: "Careers · MolTrace",
  description:
    "We hire the way we ship — deliberately, with clear gates. Real Phase work, transparent hiring rubric, four-stage interview, geo-parity compensation.",
  alternates: { canonical: "/careers" },
  openGraph: {
    title: "Careers · MolTrace",
    description:
      "Regulatory-grade engineering, promotion-gate culture, multi-modal science. Honest about what's open. Honest about what isn't.",
    type: "website",
  },
}

export default function CareersRoute() {
  return <CareersPage />
}

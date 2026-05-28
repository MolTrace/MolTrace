import type { Metadata } from "next"
import { SpectroscopyPage } from "@/components/marketing/spectroscopy-page"

export const metadata: Metadata = {
  title: "Spectroscopy · MolTrace",
  description:
    "SpectraCheck is the spectroscopy intelligence engine inside MolTrace — NMR, LC-MS, HRMS, MS/MS as one evidence stack, audit-grade from raw FID to regulatory-ready report.",
  alternates: { canonical: "/spectroscopy" },
  openGraph: {
    title: "Spectroscopy · MolTrace",
    description:
      "Spectroscopy with an audit trail. Six-stage pipeline, four modalities, 39-layer evidence stack, two detectors behind one envelope.",
    type: "website",
  },
}

export default function SpectroscopyRoute() {
  return <SpectroscopyPage />
}

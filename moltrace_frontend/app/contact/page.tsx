import type { Metadata } from "next"
import { ContactPage } from "@/components/marketing/contact-page"

export const metadata: Metadata = {
  title: "Contact · MolTrace",
  description:
    "Get in touch with MolTrace — request a demo, open a support ticket, or reach our security, partnership, and press teams.",
  alternates: { canonical: "/contact" },
  openGraph: {
    title: "Contact · MolTrace",
    description:
      "Demo requests, support tickets, partnerships, and security disclosures — routed to the right MolTrace team.",
    type: "website",
  },
}

export default function ContactRoute() {
  return <ContactPage />
}

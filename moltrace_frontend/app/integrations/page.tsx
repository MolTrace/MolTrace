import type { Metadata } from "next"
import { IntegrationsPage } from "@/components/marketing/integrations-page"

export const metadata: Metadata = {
  title: "Integrations · MolTrace",
  description:
    "Your existing stack — spoken natively, end to end. Instruments, LIMS, ELN, identity providers, pharmacopoeia feeds. One audit ledger across every connector.",
  alternates: { canonical: "/integrations" },
  openGraph: {
    title: "Integrations · MolTrace",
    description:
      "Bruker, Agilent, LabWare, Benchling, Okta, USP-NF — connected via typed mappings, signed webhooks, and a single connector ledger.",
    type: "website",
  },
}

export default function IntegrationsRoute() {
  return <IntegrationsPage />
}

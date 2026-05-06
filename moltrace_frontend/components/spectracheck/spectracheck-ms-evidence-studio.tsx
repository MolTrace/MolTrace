"use client"

import { SpectraCheckLcmsWorkflow } from "@/components/spectracheck/spectracheck-lcms-workflow"
import { SpectraCheckMsEvidence } from "@/components/spectracheck/spectracheck-ms-evidence"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { InfoTooltip } from "@/components/ui/info-tooltip"

type Props = {
  sampleId: string
  candidatesText: string
}

/**
 * MS Evidence Studio: composes existing MS and LC-MS modules with progressive disclosure.
 * Shared session fields remain on the NMR text + candidates tab only.
 */
export function SpectraCheckMsEvidenceStudio({ sampleId, candidatesText }: Props) {
  return (
    <div className="min-w-0 space-y-6">
      <Card className="min-w-0 border-muted">
        <CardHeader className="space-y-2">
          <CardTitle className="flex flex-wrap items-center gap-2 text-lg">
            MS Evidence Studio
            <InfoTooltip
              label="About MS Evidence Studio"
              content="High-resolution MS and MS/MS tools use shared sample ID and candidate structures from the session. Expand LC-MS when you need import through the consensus bridge."
            />
          </CardTitle>
          <CardDescription>
            HRMS exact mass, formula search, adduct and isotope inference, processed MS/MS, and fragmentation tree run in
            the panel below. LC-MS import, feature workflows, and the unified confidence bridge are grouped under
            Advanced LC-MS.
          </CardDescription>
        </CardHeader>
      </Card>

      <div className="min-w-0">
        <SpectraCheckMsEvidence sampleId={sampleId} candidatesText={candidatesText} />
      </div>

      <Accordion type="single" collapsible className="w-full min-w-0 rounded-lg border bg-card px-1">
        <AccordionItem value="lcms-advanced" className="border-none px-3">
          <AccordionTrigger className="py-4 text-left text-base font-medium hover:no-underline">
            Advanced LC-MS (import bridge through confidence bridge)
          </AccordionTrigger>
          <AccordionContent className="min-w-0 pb-6 pt-0">
            <p className="mb-4 text-sm text-muted-foreground">
              LC-MS import bridge, feature detection, grouping / blank subtraction / RT alignment, feature-family
              consensus, library dereplication, and LC-MS → unified confidence bridge.
            </p>
            <div className="min-w-0 overflow-x-auto">
              <SpectraCheckLcmsWorkflow sampleId={sampleId} candidatesText={candidatesText} />
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  )
}

"use client"

import { SpectraCheckLcmsWorkflow } from "@/components/spectracheck/spectracheck-lcms-workflow"
import { SpectraCheckMsEvidence } from "@/components/spectracheck/spectracheck-ms-evidence"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Atom, Network, Settings2 } from "lucide-react"
import {
  COMPOUND_CLASS_UNSPECIFIED,
  type CompoundClassValue,
} from "@/src/lib/spectracheck/compound-classes"

type Props = {
  sampleId: string
  candidatesText: string
  /**
   * Compound-class hint from the shared NMR text + candidates tab. Forwarded
   * to MS / LC-MS workflows as endpoint metadata. MS scoring itself is left
   * unchanged unless a route explicitly consumes the hint.
   */
  compoundClass?: CompoundClassValue
}

/**
 * MS Evidence Studio: composes existing MS and LC-MS modules with progressive disclosure.
 * Shared session fields remain on the NMR text + candidates tab only.
 */
export function SpectraCheckMsEvidenceStudio({
  sampleId,
  candidatesText,
  compoundClass = COMPOUND_CLASS_UNSPECIFIED,
}: Props) {
  return (
    <div className="min-w-0 space-y-12">
      {/* Header */}
      <div className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-teal)" }}
        >
          Spectroscopy · MS Studio
        </p>
        <h2 className="inline-flex items-center gap-2 font-mono text-xl font-bold tracking-tight">
          MS Evidence Studio
          <InfoTooltip
            label="About MS Evidence Studio"
            content="High-resolution MS and MS/MS tools use shared sample ID and candidate structures from the session. Expand LC-MS when you need import through the consensus bridge."
          />
        </h2>
        <p className="text-sm text-muted-foreground">
          HRMS exact mass, formula search, adduct & isotope inference, processed MS/MS, and fragmentation
          tree — plus optional LC-MS pipeline & unified confidence bridge.
        </p>
      </div>

      {/* Step 1 — Setup context */}
      <ModuleCard
        accent="teal"
        eyebrow="MS · Step 1 · Setup"
        title="Inputs from shared session"
        icon={Atom}
        description="MS analyzers use the sample ID and candidates from the workspace header — no extra inputs needed at this level."
        className="min-w-0"
      >
        <div className="grid gap-2 sm:grid-cols-2">
          <div
            className="rounded-md border px-3 py-2"
            style={{ borderColor: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
          >
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--mt-teal)" }}>
              Sample ID
            </p>
            <p className="mt-1 truncate font-mono text-xs">{sampleId.trim() || "(empty)"}</p>
          </div>
          <div
            className="rounded-md border px-3 py-2"
            style={{ borderColor: "var(--mt-teal)", backgroundColor: "var(--mt-teal-soft)" }}
          >
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--mt-teal)" }}>
              Candidates
            </p>
            <p className="mt-1 truncate font-mono text-xs">
              {candidatesText.split("\n").filter((l) => l.trim()).length} candidate{candidatesText.split("\n").filter((l) => l.trim()).length === 1 ? "" : "s"} ready
            </p>
          </div>
        </div>
      </ModuleCard>

      {/* Step 2 — Run MS evidence panel */}
      <ModuleCard
        accent="teal"
        eyebrow="MS · Step 2 · Analyze"
        title="HRMS, MS/MS & fragmentation"
        icon={Network}
        description="Exact mass, formula search, adduct/isotope inference, processed MS/MS, and fragmentation tree."
        className="min-w-0"
      >
        <div className="min-w-0">
          <SpectraCheckMsEvidence
            sampleId={sampleId}
            candidatesText={candidatesText}
            compoundClass={compoundClass}
          />
        </div>
      </ModuleCard>

      {/* Step 3 — Advanced LC-MS pipeline */}
      <ModuleCard
        accent="teal"
        eyebrow="MS · Step 3 · Advanced"
        title="LC-MS pipeline & confidence bridge"
        icon={Settings2}
        description="Optional: LC-MS import, feature detection, grouping / blank-subtraction / RT alignment, family consensus, library dereplication, and LC-MS → unified confidence bridge."
        className="min-w-0"
      >
        <Accordion type="single" collapsible className="w-full min-w-0 rounded-lg border bg-card px-1">
          <AccordionItem value="lcms-advanced" className="border-none px-3">
            <AccordionTrigger className="py-4 text-left text-base font-medium hover:no-underline">
              Open LC-MS workflow
            </AccordionTrigger>
            <AccordionContent className="min-w-0 pb-6 pt-0">
              <div className="min-w-0 overflow-x-auto">
                <SpectraCheckLcmsWorkflow
                  sampleId={sampleId}
                  candidatesText={candidatesText}
                  compoundClass={compoundClass}
                />
              </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </ModuleCard>
    </div>
  )
}

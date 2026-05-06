import { AppShell } from "@/components/app/app-shell"
import { AiModulePredictionAugmentation } from "@/components/ai/ai-module-prediction-augmentation"
import { RegulatoryDossierWorkspace } from "@/components/regulatory-hub/regulatory-dossier-workspace"

export default function RegulatoryDossierPage() {
  return (
    <AppShell>
      <div className="space-y-6">
        <RegulatoryDossierWorkspace />
        <AiModulePredictionAugmentation
          moduleKey="regulatory"
          moduleTitle="Regulatory Dossier"
          serviceOptions={[
            {
              id: "regulatory-extraction-classifier",
              label: "regulatory extraction classifier",
              serviceKey: "regulatory_extraction_classifier",
              taskKey: "regulatory_extraction_classification",
            },
            {
              id: "citation-support-classifier",
              label: "citation support classifier",
              serviceKey: "regulatory_citation_support_classifier",
              taskKey: "citation_support_classification",
            },
            {
              id: "knowledge-quality-scorer",
              label: "knowledge quality scorer",
              serviceKey: "regulatory_knowledge_quality_scorer",
              taskKey: "knowledge_quality_scoring",
            },
          ]}
          summarySeed={{ module_scope: "regulatory_dossier", summary_type: "dossier_summary" }}
        />
      </div>
    </AppShell>
  )
}

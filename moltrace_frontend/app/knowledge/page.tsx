import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { AiModulePredictionAugmentation } from "@/components/ai/ai-module-prediction-augmentation"
import { KnowledgeLibraryLanding } from "@/components/knowledge/knowledge-library-landing"

export default function KnowledgeLibraryPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading Knowledge Library…</div>}>
        <div className="space-y-6">
          <KnowledgeLibraryLanding />
          <AiModulePredictionAugmentation
            moduleKey="knowledge_extraction"
            moduleTitle="Knowledge"
            serviceOptions={[
              {
                id: "record-quality-scorer",
                label: "record quality scorer",
                serviceKey: "knowledge_record_quality_scorer",
                taskKey: "record_quality_scoring",
              },
              {
                id: "extraction-confidence-scorer",
                label: "extraction confidence scorer",
                serviceKey: "knowledge_extraction_confidence_scorer",
                taskKey: "extraction_confidence_scoring",
              },
            ]}
            summarySeed={{ module_scope: "knowledge_library", summary_type: "record_summary" }}
          />
        </div>
      </Suspense>
    </AppShell>
  )
}

"use client"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { AiServicesDashboard } from "@/components/ai/ai-services-dashboard"
import { AiModulePredictionAugmentation } from "@/components/ai/ai-module-prediction-augmentation"
import { KnowledgeLibraryLanding } from "@/components/knowledge/knowledge-library-landing"

export function MlAiInterfaceWorkspace() {
  return (
    <div className="space-y-6">
      <Tabs defaultValue="ai_services" className="space-y-6">
        <TabsList>
          <TabsTrigger value="ai_services">AI Services</TabsTrigger>
          <TabsTrigger value="knowledge_library">Knowledge Library</TabsTrigger>
        </TabsList>
        <TabsContent value="ai_services">
          <AiServicesDashboard />
        </TabsContent>
        <TabsContent value="knowledge_library">
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
        </TabsContent>
      </Tabs>
    </div>
  )
}

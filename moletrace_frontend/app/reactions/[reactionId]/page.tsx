import { AppShell } from "@/components/app/app-shell"
import { AiModulePredictionAugmentation } from "@/components/ai/ai-module-prediction-augmentation"
import { ReactionProjectDetail } from "@/components/reaction-optimization/reaction-project-detail"

export default function ReactionProjectDetailPage() {
  return (
    <AppShell>
      <div className="space-y-6">
        <ReactionProjectDetail />
        <AiModulePredictionAugmentation
          moduleKey="reaction_optimization"
          moduleTitle="Reaction Studio"
          serviceOptions={[
            {
              id: "reaction-outcome-predictor",
              label: "reaction outcome predictor",
              serviceKey: "reaction_outcome_predictor",
              taskKey: "reaction_outcome_prediction",
            },
            {
              id: "reaction-recommendation-scorer",
              label: "reaction recommendation scorer",
              serviceKey: "reaction_recommendation_scorer",
              taskKey: "reaction_recommendation_scoring",
            },
          ]}
          summarySeed={{ module_scope: "reaction_studio", summary_type: "reaction_summary" }}
        />
      </div>
    </AppShell>
  )
}

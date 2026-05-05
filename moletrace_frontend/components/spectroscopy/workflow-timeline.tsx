"use client"

import { cn } from "@/lib/utils"
import { Upload, Cog, BarChart3, ListOrdered, UserCheck, FileText, Check } from "lucide-react"

const steps = [
  { icon: Upload, label: "Import", status: "complete" },
  { icon: Cog, label: "Process", status: "complete" },
  { icon: BarChart3, label: "Peak Pick", status: "complete" },
  { icon: ListOrdered, label: "Candidate Rank", status: "current" },
  { icon: UserCheck, label: "Review", status: "pending" },
  { icon: FileText, label: "Report", status: "pending" },
]

export function WorkflowTimeline() {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex items-center justify-between">
        {steps.map((step, index) => (
          <div key={step.label} className="flex items-center">
            <div className="flex flex-col items-center gap-1.5">
              <div
                className={cn(
                  "flex h-8 w-8 items-center justify-center rounded-full border-2 transition-colors",
                  step.status === "complete" && "border-success bg-success text-success-foreground",
                  step.status === "current" && "border-accent bg-accent/10 text-accent",
                  step.status === "pending" && "border-muted-foreground/30 text-muted-foreground"
                )}
              >
                {step.status === "complete" ? (
                  <Check className="h-4 w-4" />
                ) : (
                  <step.icon className="h-4 w-4" />
                )}
              </div>
              <span
                className={cn(
                  "text-xs font-medium",
                  step.status === "current" && "text-accent",
                  step.status === "pending" && "text-muted-foreground"
                )}
              >
                {step.label}
              </span>
            </div>
            {index < steps.length - 1 && (
              <div
                className={cn(
                  "mx-2 h-0.5 w-12 sm:w-20 lg:w-32",
                  step.status === "complete" ? "bg-success" : "bg-muted"
                )}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

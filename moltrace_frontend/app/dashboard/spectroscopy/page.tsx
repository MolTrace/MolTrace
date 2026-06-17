"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"
import { Download, Play } from "lucide-react"
import { SpectrumViewer } from "@/components/spectroscopy/spectrum-viewer"
import { CandidateTable } from "@/components/spectroscopy/candidate-table"
import { EvidencePanel } from "@/components/spectroscopy/evidence-panel"
import { FilePanel } from "@/components/spectroscopy/file-panel"
import { WorkflowTimeline } from "@/components/spectroscopy/workflow-timeline"

export default function SpectroscopyPage() {
  const [selectedCandidate, setSelectedCandidate] = useState(0)

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col gap-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal-ink)" }}
            >
              MolTrace · Dashboard · Spectroscopy
            </p>
            <h1 className="font-mono text-lg font-bold tracking-tight">NMR-2024-0847</h1>
            <p className="text-sm text-muted-foreground">API-Q4-BATCH-12 · demo session</p>
          </div>
          <div className="flex gap-2">
            <Badge variant="outline">1H NMR</Badge>
            <Badge variant="outline">13C NMR</Badge>
            <Badge variant="outline">MS/MS</Badge>
          </div>
          <Badge variant="secondary" className="gap-1">
            <Play className="h-3 w-3" />
            Running
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          <Select defaultValue="all">
            <SelectTrigger className="w-32">
              <SelectValue placeholder="Overlay" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Spectra</SelectItem>
              <SelectItem value="observed">Observed Only</SelectItem>
              <SelectItem value="predicted">Predicted Only</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" className="gap-2">
            <Download className="h-4 w-4" />
            Export Report
          </Button>
        </div>
      </div>

      {/* Main Content */}
      <ResizablePanelGroup direction="horizontal" className="flex-1 rounded-lg border">
        {/* Left Panel - Files & Metadata */}
        <ResizablePanel defaultSize={20} minSize={15} maxSize={30}>
          <FilePanel />
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Center Panel - Spectrum & Candidates */}
        <ResizablePanel defaultSize={55} minSize={40}>
          <div className="flex h-full flex-col">
            <div className="flex-1 border-b">
              <SpectrumViewer />
            </div>
            <div className="h-[280px] overflow-auto">
              <CandidateTable 
                selectedIndex={selectedCandidate} 
                onSelect={setSelectedCandidate} 
              />
            </div>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Right Panel - Evidence */}
        <ResizablePanel defaultSize={25} minSize={20} maxSize={35}>
          <EvidencePanel candidateIndex={selectedCandidate} />
        </ResizablePanel>
      </ResizablePanelGroup>

      {/* Bottom Timeline */}
      <WorkflowTimeline />
    </div>
  )
}

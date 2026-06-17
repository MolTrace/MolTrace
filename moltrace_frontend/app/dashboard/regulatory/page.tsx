"use client"

import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Checkbox } from "@/components/ui/checkbox"
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
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileText,
  Download,
  ExternalLink,
  BookOpen,
  User,
  Calendar,
  ChevronRight,
  Shield,
  Globe,
} from "lucide-react"

const dossierNav = [
  { id: "identity", label: "Identity", count: 3 },
  { id: "analytical", label: "Analytical Evidence", count: 12 },
  { id: "impurities", label: "Impurities", count: 5 },
  { id: "safety", label: "Safety", count: 8 },
  { id: "claims", label: "Claims", count: 4 },
  { id: "submissions", label: "Submissions", count: 2 },
  { id: "changelog", label: "Change Log", count: 15 },
]

const requirements = [
  {
    id: 1,
    requirement: "Spectroscopic Identity Confirmation",
    status: "complete",
    owner: "Dr. Chen",
    dueDate: "2024-01-15",
    evidence: 3,
  },
  {
    id: 2,
    requirement: "Impurity Profiling (ICH Q3A)",
    status: "complete",
    owner: "Dr. Patel",
    dueDate: "2024-01-20",
    evidence: 5,
  },
  {
    id: 3,
    requirement: "Residual Solvent Analysis",
    status: "in_progress",
    owner: "J. Smith",
    dueDate: "2024-02-01",
    evidence: 2,
  },
  {
    id: 4,
    requirement: "Genotoxic Impurity Assessment",
    status: "pending",
    owner: "Dr. Kim",
    dueDate: "2024-02-15",
    evidence: 0,
  },
  {
    id: 5,
    requirement: "Stability Studies (ICH Q1A)",
    status: "pending",
    owner: "M. Johnson",
    dueDate: "2024-03-01",
    evidence: 0,
  },
  {
    id: 6,
    requirement: "Method Validation Report",
    status: "in_progress",
    owner: "Dr. Chen",
    dueDate: "2024-02-10",
    evidence: 4,
  },
]

const citations = [
  {
    id: 1,
    source: "USP <621> Chromatography",
    type: "Pharmacopeia",
    confidence: "High",
    jurisdiction: "US",
    date: "2023-12",
    notes: "Method compliant with current USP requirements.",
  },
  {
    id: 2,
    source: "ICH Q3A(R2) Impurities",
    type: "Guideline",
    confidence: "High",
    jurisdiction: "ICH",
    date: "2023-11",
    notes: "All identified impurities below reporting threshold.",
  },
  {
    id: 3,
    source: "EMA/CHMP/ICH/82260/2006",
    type: "Guideline",
    confidence: "Medium",
    jurisdiction: "EU",
    date: "2024-01",
    notes: "Requires additional stability data for EU submission.",
  },
]

export default function RegulatoryPage() {
  const [selectedSection, setSelectedSection] = useState("analytical")

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col gap-4">
      {/* Warning Banner */}
      <div className="rounded-lg border border-warning/30 bg-warning/5 p-3">
        <div className="flex items-start gap-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <div className="flex-1">
            <div className="text-sm font-medium">AI-Generated Interpretation</div>
            <p className="text-xs text-muted-foreground">
              All regulatory assessments require qualified human review before submission. 
              This analysis does not constitute regulatory advice.
            </p>
          </div>
        </div>
      </div>

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-cyan-ink)" }}
            >
              MolTrace · Dashboard · Regulatory
            </p>
            <h1 className="font-mono text-lg font-bold tracking-tight">REG-2024-0445</h1>
            <p className="text-sm text-muted-foreground">API-Q4-Compound-A Regulatory Dossier · demo dossier</p>
          </div>
          <div className="flex items-center gap-2">
            <Select defaultValue="us">
              <SelectTrigger className="h-8 w-32">
                <Globe className="mr-2 h-4 w-4" />
                <SelectValue placeholder="Jurisdiction" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="us">US (FDA)</SelectItem>
                <SelectItem value="eu">EU (EMA)</SelectItem>
                <SelectItem value="jp">Japan (PMDA)</SelectItem>
                <SelectItem value="ich">ICH</SelectItem>
              </SelectContent>
            </Select>
            <Badge variant="secondary" className="gap-1">
              <Shield className="h-3 w-3" />
              Low Risk
            </Badge>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Last updated: 2 hours ago</span>
          <Button variant="outline" size="sm" className="gap-2">
            <Download className="h-4 w-4" />
            PDF Report
          </Button>
          <Button variant="outline" size="sm" className="gap-2">
            <FileText className="h-4 w-4" />
            Word Report
          </Button>
          <Button size="sm" className="gap-2">
            <Download className="h-4 w-4" />
            Audit Package
          </Button>
        </div>
      </div>

      <ResizablePanelGroup direction="horizontal" className="flex-1 rounded-lg border">
        {/* Left Panel - Dossier Navigation */}
        <ResizablePanel defaultSize={18} minSize={15} maxSize={25}>
          <div className="flex h-full flex-col">
            <div className="border-b px-4 py-3">
              <h3 className="font-semibold">Dossier Sections</h3>
            </div>
            <ScrollArea className="flex-1">
              <div className="p-2">
                {dossierNav.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setSelectedSection(item.id)}
                    className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm transition-colors ${
                      selectedSection === item.id
                        ? "bg-secondary font-medium"
                        : "text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    <span>{item.label}</span>
                    <Badge variant="outline" className="ml-2 h-5 px-1.5 text-xs">
                      {item.count}
                    </Badge>
                  </button>
                ))}
              </div>
            </ScrollArea>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Center Panel - Requirements Checklist */}
        <ResizablePanel defaultSize={52} minSize={40}>
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <div>
                <h3 className="font-semibold">Regulatory Requirements</h3>
                <p className="text-xs text-muted-foreground">
                  {requirements.filter(r => r.status === "complete").length} of {requirements.length} complete
                </p>
              </div>
              <Progress 
                value={(requirements.filter(r => r.status === "complete").length / requirements.length) * 100} 
                className="h-2 w-32" 
              />
            </div>
            <ScrollArea className="flex-1">
              <div className="p-4">
                <div className="space-y-2">
                  {requirements.map((req) => (
                    <Card key={req.id} className="overflow-hidden">
                      <div className="flex items-start gap-3 p-4">
                        <Checkbox 
                          checked={req.status === "complete"}
                          disabled={req.status === "pending"}
                          className="mt-0.5"
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-start justify-between gap-2">
                            <div className="text-sm font-medium">{req.requirement}</div>
                            {req.status === "complete" && (
                              <Badge className="shrink-0 gap-1 bg-success text-success-foreground">
                                <CheckCircle2 className="h-3 w-3" />
                                Complete
                              </Badge>
                            )}
                            {req.status === "in_progress" && (
                              <Badge className="shrink-0 gap-1" variant="secondary">
                                <Clock className="h-3 w-3" />
                                In Progress
                              </Badge>
                            )}
                            {req.status === "pending" && (
                              <Badge variant="outline" className="shrink-0">
                                Pending
                              </Badge>
                            )}
                          </div>
                          <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
                            <div className="flex items-center gap-1">
                              <User className="h-3 w-3" />
                              {req.owner}
                            </div>
                            <div className="flex items-center gap-1">
                              <Calendar className="h-3 w-3" />
                              {req.dueDate}
                            </div>
                            <div className="flex items-center gap-1">
                              <BookOpen className="h-3 w-3" />
                              {req.evidence} evidence linked
                            </div>
                          </div>
                        </div>
                        <Button variant="ghost" size="icon" className="shrink-0">
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </div>
                    </Card>
                  ))}
                </div>
              </div>
            </ScrollArea>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Right Panel - Cited Evidence */}
        <ResizablePanel defaultSize={30} minSize={25} maxSize={40}>
          <div className="flex h-full flex-col">
            <div className="border-b px-4 py-3">
              <h3 className="font-semibold">Cited Evidence</h3>
              <p className="text-xs text-muted-foreground">
                Supporting documentation and references
              </p>
            </div>
            <ScrollArea className="flex-1">
              <div className="space-y-3 p-4">
                {citations.map((citation) => (
                  <Card key={citation.id}>
                    <CardHeader className="p-3 pb-2">
                      <div className="flex items-start justify-between gap-2">
                        <CardTitle className="text-sm">{citation.source}</CardTitle>
                        <Badge 
                          variant="outline" 
                          className={
                            citation.confidence === "High" 
                              ? "border-success/50 text-success" 
                              : "border-warning/50 text-warning"
                          }
                        >
                          {citation.confidence}
                        </Badge>
                      </div>
                      <CardDescription className="flex items-center gap-2 text-xs">
                        <Badge variant="secondary" className="text-[10px]">{citation.type}</Badge>
                        <span>{citation.jurisdiction}</span>
                        <span>·</span>
                        <span>{citation.date}</span>
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="p-3 pt-0">
                      <div className="rounded bg-muted/50 p-2">
                        <div className="mb-1 text-[10px] font-medium text-muted-foreground">
                          Reviewer Notes
                        </div>
                        <p className="text-xs">{citation.notes}</p>
                      </div>
                      <Button variant="ghost" size="sm" className="mt-2 h-7 w-full gap-1 text-xs">
                        <ExternalLink className="h-3 w-3" />
                        View Source
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </ScrollArea>
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}

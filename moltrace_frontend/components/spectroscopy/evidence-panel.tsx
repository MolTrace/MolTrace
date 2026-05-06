"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  BookOpen,
  ThumbsUp,
  ThumbsDown,
  MessageSquare,
} from "lucide-react"

const candidateData = [
  {
    formula: "C₁₂H₁₆N₂O₃",
    confidence: 87,
    matchingPeaks: [
      { ppm: "1.23", assignment: "CH3 (triplet)", match: "exact" },
      { ppm: "3.82", assignment: "OCH3", match: "exact" },
      { ppm: "6.92", assignment: "Ar-H", match: "close" },
      { ppm: "7.24", assignment: "Ar-H", match: "exact" },
    ],
    missingPeaks: [
      { expected: "142.3 ppm (13C)", reason: "Quaternary carbon not observed" },
    ],
    contradictions: [
      { type: "Missing signal", description: "Expected C-13 peak at 142 ppm not observed in spectrum" },
    ],
    citations: [
      { source: "SDBS Database", id: "#12847", confidence: "High" },
      { source: "J. Org. Chem. 2023", id: "88, 4521", confidence: "Medium" },
      { source: "HMDB", id: "HMDB0062458", confidence: "High" },
    ],
  },
]

interface EvidencePanelProps {
  candidateIndex: number
}

export function EvidencePanel({ candidateIndex }: EvidencePanelProps) {
  const data = candidateData[0] // Would use candidateIndex in real app

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-4 py-3">
        <h3 className="font-semibold">Evidence & Reasoning</h3>
        <p className="text-xs text-muted-foreground">Candidate #{candidateIndex + 1}</p>
      </div>

      <ScrollArea className="flex-1">
        <div className="space-y-4 p-4">
          {/* Confidence Gauge */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Overall Confidence</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="relative pt-1">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Low</span>
                  <span className="font-mono text-2xl font-semibold text-accent">
                    {data.confidence}%
                  </span>
                  <span className="text-xs text-muted-foreground">High</span>
                </div>
                <Progress value={data.confidence} className="h-3" />
                <div className="mt-2 flex justify-between text-[10px] text-muted-foreground">
                  <span>0</span>
                  <span>50</span>
                  <span>100</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Evidence Accordion */}
          <Accordion type="multiple" defaultValue={["peaks", "issues", "citations"]} className="space-y-2">
            {/* Matching Peaks */}
            <AccordionItem value="peaks" className="rounded-lg border px-3">
              <AccordionTrigger className="py-3 text-sm hover:no-underline">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-success" />
                  Key Matching Peaks ({data.matchingPeaks.length})
                </div>
              </AccordionTrigger>
              <AccordionContent className="pb-3">
                <div className="space-y-2">
                  {data.matchingPeaks.map((peak, i) => (
                    <div key={i} className="flex items-center justify-between rounded bg-muted/50 px-2 py-1.5 text-xs">
                      <div className="font-mono">{peak.ppm} ppm</div>
                      <div className="text-muted-foreground">{peak.assignment}</div>
                      <Badge
                        variant="outline"
                        className={
                          peak.match === "exact"
                            ? "border-success/50 text-success"
                            : "border-warning/50 text-warning"
                        }
                      >
                        {peak.match}
                      </Badge>
                    </div>
                  ))}
                </div>
              </AccordionContent>
            </AccordionItem>

            {/* Missing Peaks */}
            {data.missingPeaks.length > 0 && (
              <AccordionItem value="missing" className="rounded-lg border px-3">
                <AccordionTrigger className="py-3 text-sm hover:no-underline">
                  <div className="flex items-center gap-2">
                    <XCircle className="h-4 w-4 text-muted-foreground" />
                    Missing Peaks ({data.missingPeaks.length})
                  </div>
                </AccordionTrigger>
                <AccordionContent className="pb-3">
                  <div className="space-y-2">
                    {data.missingPeaks.map((peak, i) => (
                      <div key={i} className="rounded bg-muted/50 px-2 py-1.5 text-xs">
                        <div className="font-medium">{peak.expected}</div>
                        <div className="text-muted-foreground">{peak.reason}</div>
                      </div>
                    ))}
                  </div>
                </AccordionContent>
              </AccordionItem>
            )}

            {/* Contradictions */}
            {data.contradictions.length > 0 && (
              <AccordionItem value="issues" className="rounded-lg border border-warning/30 bg-warning/5 px-3">
                <AccordionTrigger className="py-3 text-sm hover:no-underline">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-warning" />
                    Contradictions ({data.contradictions.length})
                  </div>
                </AccordionTrigger>
                <AccordionContent className="pb-3">
                  <div className="space-y-2">
                    {data.contradictions.map((issue, i) => (
                      <div key={i} className="rounded bg-background px-2 py-1.5 text-xs">
                        <div className="font-medium text-warning">{issue.type}</div>
                        <div className="text-muted-foreground">{issue.description}</div>
                      </div>
                    ))}
                  </div>
                </AccordionContent>
              </AccordionItem>
            )}

            {/* Citations */}
            <AccordionItem value="citations" className="rounded-lg border px-3">
              <AccordionTrigger className="py-3 text-sm hover:no-underline">
                <div className="flex items-center gap-2">
                  <BookOpen className="h-4 w-4 text-muted-foreground" />
                  Citations ({data.citations.length})
                </div>
              </AccordionTrigger>
              <AccordionContent className="pb-3">
                <div className="space-y-2">
                  {data.citations.map((citation, i) => (
                    <div key={i} className="flex items-center justify-between rounded bg-muted/50 px-2 py-1.5 text-xs">
                      <div>
                        <div className="font-medium">{citation.source}</div>
                        <div className="text-muted-foreground">{citation.id}</div>
                      </div>
                      <Badge variant="outline">{citation.confidence}</Badge>
                    </div>
                  ))}
                </div>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </div>
      </ScrollArea>

      {/* Human Approval Controls */}
      <div className="border-t p-4">
        <div className="mb-3 text-xs text-muted-foreground">Human Approval Required</div>
        <div className="flex gap-2">
          <Button className="flex-1 gap-1" variant="outline">
            <ThumbsDown className="h-4 w-4" />
            Reject
          </Button>
          <Button className="flex-1 gap-1">
            <ThumbsUp className="h-4 w-4" />
            Approve
          </Button>
        </div>
        <Button variant="ghost" className="mt-2 w-full gap-1 text-xs" size="sm">
          <MessageSquare className="h-3 w-3" />
          Add Review Note
        </Button>
      </div>
    </div>
  )
}

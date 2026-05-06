"use client"

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/utils"
import { CheckCircle2, AlertTriangle, Clock } from "lucide-react"

const candidates = [
  {
    rank: 1,
    formula: "C₁₂H₁₆N₂O₃",
    mw: 236.27,
    confidence: 87,
    nmrFit: 92,
    msmsFit: 89,
    lcmsSupport: 78,
    contradictions: 1,
    reviewState: "pending",
  },
  {
    rank: 2,
    formula: "C₁₂H₁₆N₂O₃",
    mw: 236.27,
    confidence: 74,
    nmrFit: 78,
    msmsFit: 82,
    lcmsSupport: 65,
    contradictions: 2,
    reviewState: "rejected",
  },
  {
    rank: 3,
    formula: "C₁₁H₁₄N₂O₄",
    mw: 238.24,
    confidence: 68,
    nmrFit: 72,
    msmsFit: 74,
    lcmsSupport: 58,
    contradictions: 3,
    reviewState: "pending",
  },
  {
    rank: 4,
    formula: "C₁₃H₁₈N₂O₂",
    mw: 234.29,
    confidence: 52,
    nmrFit: 58,
    msmsFit: 62,
    lcmsSupport: 45,
    contradictions: 4,
    reviewState: "pending",
  },
]

interface CandidateTableProps {
  selectedIndex: number
  onSelect: (index: number) => void
}

export function CandidateTable({ selectedIndex, onSelect }: CandidateTableProps) {
  return (
    <div className="h-full">
      <div className="sticky top-0 flex items-center justify-between border-b bg-background px-4 py-2">
        <h3 className="text-sm font-medium">Candidate Structure Ranking</h3>
        <Badge variant="outline">{candidates.length} candidates</Badge>
      </div>
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-12">Rank</TableHead>
            <TableHead className="w-16">Structure</TableHead>
            <TableHead>Formula</TableHead>
            <TableHead>Confidence</TableHead>
            <TableHead>NMR Fit</TableHead>
            <TableHead>MS/MS Fit</TableHead>
            <TableHead>LC-MS Family</TableHead>
            <TableHead>Issues</TableHead>
            <TableHead>Review</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {candidates.map((candidate, index) => (
            <TableRow
              key={candidate.rank}
              className={cn(
                "cursor-pointer",
                selectedIndex === index && "bg-muted"
              )}
              onClick={() => onSelect(index)}
            >
              <TableCell className="font-medium">#{candidate.rank}</TableCell>
              <TableCell>
                <div className="flex h-10 w-10 items-center justify-center rounded border bg-muted/50">
                  <svg viewBox="0 0 40 40" className="h-8 w-8">
                    {/* Simple hexagon placeholder for structure */}
                    <polygon
                      points="20,5 35,15 35,30 20,40 5,30 5,15"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      className="text-muted-foreground"
                    />
                    <line x1="20" y1="5" x2="20" y2="0" stroke="currentColor" strokeWidth="1" className="text-muted-foreground" />
                    <line x1="35" y1="22" x2="40" y2="22" stroke="currentColor" strokeWidth="1" className="text-muted-foreground" />
                  </svg>
                </div>
              </TableCell>
              <TableCell>
                <div className="font-mono text-sm">{candidate.formula}</div>
                <div className="text-xs text-muted-foreground">MW: {candidate.mw}</div>
              </TableCell>
              <TableCell>
                <div className="flex items-center gap-2">
                  <Progress value={candidate.confidence} className="h-1.5 w-12" />
                  <span className="font-mono text-sm">{candidate.confidence}%</span>
                </div>
              </TableCell>
              <TableCell>
                <span className={cn(
                  "font-mono text-sm",
                  candidate.nmrFit >= 80 ? "text-success" : candidate.nmrFit >= 60 ? "text-warning" : "text-destructive"
                )}>
                  {candidate.nmrFit}%
                </span>
              </TableCell>
              <TableCell>
                <span className={cn(
                  "font-mono text-sm",
                  candidate.msmsFit >= 80 ? "text-success" : candidate.msmsFit >= 60 ? "text-warning" : "text-destructive"
                )}>
                  {candidate.msmsFit}%
                </span>
              </TableCell>
              <TableCell>
                <span className={cn(
                  "font-mono text-sm",
                  candidate.lcmsSupport >= 70 ? "text-success" : candidate.lcmsSupport >= 50 ? "text-warning" : "text-muted-foreground"
                )}>
                  {candidate.lcmsSupport}%
                </span>
              </TableCell>
              <TableCell>
                {candidate.contradictions > 0 ? (
                  <Badge variant="outline" className="gap-1 border-warning/50 text-warning">
                    <AlertTriangle className="h-3 w-3" />
                    {candidate.contradictions}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="gap-1 border-success/50 text-success">
                    <CheckCircle2 className="h-3 w-3" />
                    None
                  </Badge>
                )}
              </TableCell>
              <TableCell>
                {candidate.reviewState === "approved" && (
                  <Badge className="bg-success text-success-foreground">Approved</Badge>
                )}
                {candidate.reviewState === "rejected" && (
                  <Badge variant="destructive">Rejected</Badge>
                )}
                {candidate.reviewState === "pending" && (
                  <Badge variant="secondary" className="gap-1">
                    <Clock className="h-3 w-3" />
                    Pending
                  </Badge>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

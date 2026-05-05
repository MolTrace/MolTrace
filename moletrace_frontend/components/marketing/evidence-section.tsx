import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { CheckCircle2, AlertTriangle, BookOpen, History } from "lucide-react"

export function EvidenceSection() {
  return (
    <section className="border-y bg-muted/30 py-24" id="solutions">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="grid gap-12 lg:grid-cols-2 lg:gap-16">
          <div className="flex flex-col justify-center">
            <Badge variant="outline" className="mb-4 w-fit">Evidence-First AI</Badge>
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
              Transparent reasoning. Traceable decisions.
            </h2>
            <p className="mt-4 text-lg text-muted-foreground">
              Every AI interpretation comes with confidence scores, supporting citations, 
              identified contradictions, and a complete audit trail. No black boxes.
            </p>
            <ul className="mt-8 space-y-4">
              {[
                { icon: CheckCircle2, label: "Confidence quantification with uncertainty bounds", color: "text-success" },
                { icon: BookOpen, label: "Literature citations and spectral database references", color: "text-accent" },
                { icon: AlertTriangle, label: "Automatic contradiction detection and flagging", color: "text-warning" },
                { icon: History, label: "Complete audit trail for regulatory compliance", color: "text-muted-foreground" },
              ].map((item) => (
                <li key={item.label} className="flex items-start gap-3">
                  <item.icon className={`mt-0.5 h-5 w-5 shrink-0 ${item.color}`} />
                  <span className="text-muted-foreground">{item.label}</span>
                </li>
              ))}
            </ul>
          </div>
          
          {/* Evidence Card Preview */}
          <div className="flex items-center justify-center">
            <Card className="w-full max-w-md">
              <CardHeader className="pb-4">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base font-medium">Structure Candidate #1</CardTitle>
                  <Badge variant="secondary">Requires Review</Badge>
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span className="font-mono">C₁₂H₁₆N₂O₃</span>
                  <span>·</span>
                  <span>MW: 236.27</span>
                </div>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Confidence Gauge */}
                <div>
                  <div className="mb-2 flex items-center justify-between text-sm">
                    <span className="font-medium">Overall Confidence</span>
                    <span className="font-mono text-accent">87.3%</span>
                  </div>
                  <Progress value={87.3} className="h-2" />
                </div>

                {/* Evidence Breakdown */}
                <div className="space-y-3">
                  <div className="text-sm font-medium">Evidence Breakdown</div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-md border bg-muted/50 p-3">
                      <div className="text-xs text-muted-foreground">NMR Match</div>
                      <div className="mt-1 font-mono text-sm font-medium text-success">92%</div>
                    </div>
                    <div className="rounded-md border bg-muted/50 p-3">
                      <div className="text-xs text-muted-foreground">MS/MS Fit</div>
                      <div className="mt-1 font-mono text-sm font-medium text-success">89%</div>
                    </div>
                    <div className="rounded-md border bg-muted/50 p-3">
                      <div className="text-xs text-muted-foreground">LC-MS Family</div>
                      <div className="mt-1 font-mono text-sm font-medium text-accent">78%</div>
                    </div>
                    <div className="rounded-md border bg-muted/50 p-3">
                      <div className="text-xs text-muted-foreground">Literature</div>
                      <div className="mt-1 font-mono text-sm font-medium text-success">94%</div>
                    </div>
                  </div>
                </div>

                {/* Contradictions */}
                <div className="rounded-md border border-warning/30 bg-warning/5 p-3">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                    <div>
                      <div className="text-sm font-medium">1 Contradiction Detected</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        Expected C-13 peak at 142 ppm not observed
                      </div>
                    </div>
                  </div>
                </div>

                {/* Citations */}
                <div className="space-y-2">
                  <div className="text-sm font-medium">Citations</div>
                  <div className="space-y-1 text-xs text-muted-foreground">
                    <div className="flex items-center gap-2">
                      <BookOpen className="h-3 w-3" />
                      <span>SDBS Database Entry #12847</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <BookOpen className="h-3 w-3" />
                      <span>J. Org. Chem. 2023, 88, 4521</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </section>
  )
}

"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
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
  FlaskConical, 
  Target, 
  Beaker,
  AlertTriangle,
  Sparkles,
  Play,
  Plus,
  ChevronRight,
} from "lucide-react"

const experiments = [
  { id: 1, solvent: "THF", base: "NaOH", catalyst: "Pd/C", temp: 80, time: 4, conc: 0.5, yield: 72, selectivity: 89, impurity: 2.1 },
  { id: 2, solvent: "DMF", base: "K2CO3", catalyst: "Pd/C", temp: 100, time: 6, conc: 0.3, yield: 81, selectivity: 92, impurity: 1.8 },
  { id: 3, solvent: "DMSO", base: "Et3N", catalyst: "Pd(OAc)2", temp: 90, time: 5, conc: 0.4, yield: 78, selectivity: 85, impurity: 3.2 },
  { id: 4, solvent: "THF", base: "NaOH", catalyst: "Pd(OAc)2", temp: 70, time: 8, conc: 0.6, yield: 65, selectivity: 94, impurity: 1.2 },
  { id: 5, solvent: "DMF", base: "K2CO3", catalyst: "Pd(PPh3)4", temp: 110, time: 3, conc: 0.25, yield: 88, selectivity: 91, impurity: 2.4 },
]

export default function ReactionsPage() {
  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col gap-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-violet)" }}
            >
              MolTrace · Dashboard · Reactions
            </p>
            <h1 className="font-mono text-lg font-bold tracking-tight">RXN-OPT-2024-156</h1>
            <p className="text-sm text-muted-foreground">Suzuki Coupling Optimization · demo campaign</p>
          </div>
          <div className="flex items-center gap-6 text-sm">
            <div>
              <span className="text-muted-foreground">Objective: </span>
              <span className="font-medium">Maximize Yield</span>
            </div>
            <div>
              <span className="text-muted-foreground">Best Yield: </span>
              <span className="font-mono font-medium text-success">88%</span>
            </div>
            <div>
              <span className="text-muted-foreground">Best Selectivity: </span>
              <span className="font-mono font-medium text-success">94%</span>
            </div>
            <Badge variant="secondary" className="gap-1">
              <Beaker className="h-3 w-3" />
              12 experiments
            </Badge>
          </div>
        </div>
        <Button className="gap-2">
          <Plus className="h-4 w-4" />
          Add Experiment
        </Button>
      </div>

      <ResizablePanelGroup direction="horizontal" className="flex-1 rounded-lg border">
        {/* Left Panel - Reaction & Constraints */}
        <ResizablePanel defaultSize={22} minSize={18} maxSize={30}>
          <div className="flex h-full flex-col">
            <div className="border-b px-4 py-3">
              <h3 className="font-semibold">Reaction Setup</h3>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {/* Reaction Scheme Placeholder */}
              <Card className="mb-4">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Reaction Scheme</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex h-32 items-center justify-center rounded border bg-muted/50">
                    <div className="flex items-center gap-4 text-muted-foreground">
                      <div className="text-center">
                        <div className="mb-1 flex h-12 w-12 items-center justify-center rounded border bg-background">
                          <FlaskConical className="h-6 w-6" />
                        </div>
                        <span className="text-xs">SM</span>
                      </div>
                      <ChevronRight className="h-5 w-5" />
                      <div className="rounded border bg-background px-3 py-1 text-xs">
                        Pd, Base
                      </div>
                      <ChevronRight className="h-5 w-5" />
                      <div className="text-center">
                        <div className="mb-1 flex h-12 w-12 items-center justify-center rounded border bg-background">
                          <Target className="h-6 w-6" />
                        </div>
                        <span className="text-xs">Product</span>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Constraints */}
              <Card className="mb-4">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Constraints</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Temperature</span>
                    <span className="font-mono">60-120 °C</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Reaction Time</span>
                    <span className="font-mono">2-12 h</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Concentration</span>
                    <span className="font-mono">0.1-1.0 M</span>
                  </div>
                </CardContent>
              </Card>

              {/* Budget */}
              <Card className="mb-4">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Experiment Budget</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="mb-2 flex justify-between text-xs">
                    <span className="text-muted-foreground">Used</span>
                    <span className="font-mono">12 / 20</span>
                  </div>
                  <Progress value={60} className="h-1.5" />
                </CardContent>
              </Card>

              {/* Safety Rules */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <AlertTriangle className="h-4 w-4 text-warning" />
                    Safety Rules
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-xs">
                  <div className="rounded bg-warning/10 p-2 text-warning">
                    Max temperature: 120 °C
                  </div>
                  <div className="rounded bg-warning/10 p-2 text-warning">
                    No open flames with THF
                  </div>
                  <div className="rounded bg-muted p-2 text-muted-foreground">
                    PPE required for catalyst handling
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Center Panel - Condition Matrix */}
        <ResizablePanel defaultSize={53} minSize={40}>
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <h3 className="font-semibold">Condition Matrix</h3>
              <div className="flex items-center gap-2">
                <Select defaultValue="yield">
                  <SelectTrigger className="h-8 w-28 text-xs">
                    <SelectValue placeholder="Sort by" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="yield">Sort: Yield</SelectItem>
                    <SelectItem value="selectivity">Sort: Selectivity</SelectItem>
                    <SelectItem value="id">Sort: Run Order</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex-1 overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="w-12">#</TableHead>
                    <TableHead>Solvent</TableHead>
                    <TableHead>Base</TableHead>
                    <TableHead>Catalyst</TableHead>
                    <TableHead>Temp (°C)</TableHead>
                    <TableHead>Time (h)</TableHead>
                    <TableHead>Conc (M)</TableHead>
                    <TableHead>Yield (%)</TableHead>
                    <TableHead>Select. (%)</TableHead>
                    <TableHead>Impurity (%)</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {experiments.map((exp) => (
                    <TableRow key={exp.id}>
                      <TableCell className="font-mono text-muted-foreground">{exp.id}</TableCell>
                      <TableCell>{exp.solvent}</TableCell>
                      <TableCell>{exp.base}</TableCell>
                      <TableCell className="font-mono text-xs">{exp.catalyst}</TableCell>
                      <TableCell className="font-mono">{exp.temp}</TableCell>
                      <TableCell className="font-mono">{exp.time}</TableCell>
                      <TableCell className="font-mono">{exp.conc}</TableCell>
                      <TableCell>
                        <span className={exp.yield >= 85 ? "font-medium text-success" : exp.yield >= 70 ? "text-warning" : ""}>
                          {exp.yield}%
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className={exp.selectivity >= 90 ? "font-medium text-success" : ""}>
                          {exp.selectivity}%
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className={exp.impurity <= 2 ? "text-success" : exp.impurity <= 3 ? "text-warning" : "text-destructive"}>
                          {exp.impurity}%
                        </span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {/* 3D Response Surface Placeholder */}
            <div className="border-t p-4">
              <div className="mb-3 flex items-center justify-between">
                <h4 className="text-sm font-medium">Response Surface</h4>
                <div className="flex items-center gap-2">
                  <Select defaultValue="temp">
                    <SelectTrigger className="h-7 w-24 text-xs">
                      <SelectValue placeholder="X-axis" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="temp">X: Temp</SelectItem>
                      <SelectItem value="time">X: Time</SelectItem>
                      <SelectItem value="conc">X: Conc</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select defaultValue="time">
                    <SelectTrigger className="h-7 w-24 text-xs">
                      <SelectValue placeholder="Y-axis" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="temp">Y: Temp</SelectItem>
                      <SelectItem value="time">Y: Time</SelectItem>
                      <SelectItem value="conc">Y: Conc</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select defaultValue="yield">
                    <SelectTrigger className="h-7 w-24 text-xs">
                      <SelectValue placeholder="Z-axis" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="yield">Z: Yield</SelectItem>
                      <SelectItem value="selectivity">Z: Select.</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="flex h-40 items-center justify-center rounded border bg-muted/30">
                <div className="text-center text-sm text-muted-foreground">
                  <div className="mb-2">3D Response Surface Visualization</div>
                  <div className="mx-auto grid h-24 w-40 grid-cols-5 gap-0.5">
                    {Array.from({ length: 25 }).map((_, i) => {
                      const intensity = Math.random()
                      return (
                        <div
                          key={i}
                          className="rounded-sm"
                          style={{
                            backgroundColor: `hsl(var(--accent) / ${0.2 + intensity * 0.8})`,
                          }}
                        />
                      )
                    })}
                  </div>
                  <div className="mt-2 flex justify-between text-xs">
                    <span>Low</span>
                    <span>High</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Right Panel - Next Experiment Recommendation */}
        <ResizablePanel defaultSize={25} minSize={20} maxSize={35}>
          <div className="flex h-full flex-col">
            <div className="border-b px-4 py-3">
              <h3 className="flex items-center gap-2 font-semibold">
                <Sparkles className="h-4 w-4 text-accent" />
                Next Experiment
              </h3>
            </div>
            <div className="flex-1 overflow-auto p-4">
              <Card className="border-accent/30 bg-accent/5">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">AI Recommendation</CardTitle>
                  <CardDescription className="text-xs">
                    Bayesian optimization suggests:
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Solvent</span>
                      <Badge variant="outline">DMF</Badge>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Base</span>
                      <Badge variant="outline">Cs2CO3</Badge>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Catalyst</span>
                      <Badge variant="outline">Pd(PPh3)4</Badge>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Temperature</span>
                      <span className="font-mono">105 °C</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Time</span>
                      <span className="font-mono">4.5 h</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Concentration</span>
                      <span className="font-mono">0.35 M</span>
                    </div>
                  </div>

                  <div className="space-y-3 border-t pt-3">
                    <div>
                      <div className="mb-1 flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">Predicted Yield</span>
                        <span className="font-mono font-medium text-success">91%</span>
                      </div>
                      <Progress value={91} className="h-1.5" />
                    </div>
                    <div>
                      <div className="mb-1 flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">Uncertainty</span>
                        <span className="font-mono">±4%</span>
                      </div>
                      <Progress value={20} className="h-1.5" />
                    </div>
                    <div>
                      <div className="mb-1 flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">Expected Improvement</span>
                        <span className="font-mono font-medium text-accent">+3%</span>
                      </div>
                    </div>
                  </div>

                  <div className="border-t pt-3">
                    <h4 className="mb-2 text-xs font-medium">Rationale</h4>
                    <p className="text-xs text-muted-foreground">
                      Higher temperature with longer time and Cs2CO3 base shows 
                      promising exploration of unexplored parameter space with 
                      high expected improvement based on GP surrogate model.
                    </p>
                  </div>
                </CardContent>
              </Card>

              <div className="mt-4 rounded-lg border border-warning/30 bg-warning/5 p-3">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                  <div>
                    <div className="text-xs font-medium">Human Approval Required</div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Experiment must be approved by qualified chemist before scheduling.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <div className="border-t p-4">
              <Button className="w-full gap-2">
                <Play className="h-4 w-4" />
                Approve & Schedule
              </Button>
            </div>
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}

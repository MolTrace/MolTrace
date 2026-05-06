import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Clock, FileText, CheckSquare, TrendingUp } from "lucide-react"

export function DashboardPreview() {
  return (
    <section className="border-y bg-muted/30 py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="text-center">
          <Badge variant="outline" className="mb-4">ROI Dashboard</Badge>
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Measure the impact
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-muted-foreground">
            Track hours saved, reports generated, and automation ROI across your organization.
          </p>
        </div>

        <div className="mt-12">
          <Card className="overflow-hidden">
            <CardContent className="p-6">
              <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
                {/* Hours Saved */}
                <Card className="border-0 bg-muted/50 shadow-none">
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                      <Clock className="h-4 w-4" />
                      Hours Saved This Month
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-3xl font-semibold">847</div>
                    <div className="mt-1 flex items-center gap-1 text-xs text-success">
                      <TrendingUp className="h-3 w-3" />
                      <span>+23% vs last month</span>
                    </div>
                  </CardContent>
                </Card>

                {/* Reports Generated */}
                <Card className="border-0 bg-muted/50 shadow-none">
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                      <FileText className="h-4 w-4" />
                      Reports Generated
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-3xl font-semibold">156</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Avg. 12 min generation time
                    </div>
                  </CardContent>
                </Card>

                {/* Review Steps Avoided */}
                <Card className="border-0 bg-muted/50 shadow-none">
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                      <CheckSquare className="h-4 w-4" />
                      Manual Steps Avoided
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-3xl font-semibold">2,341</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Peak picking, baseline correction
                    </div>
                  </CardContent>
                </Card>

                {/* Model Confidence */}
                <Card className="border-0 bg-muted/50 shadow-none">
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                      Model Confidence Calibration
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-baseline gap-2">
                      <div className="text-3xl font-semibold">94.2%</div>
                      <div className="text-sm text-muted-foreground">accuracy</div>
                    </div>
                    <Progress value={94.2} className="mt-2 h-1.5" />
                  </CardContent>
                </Card>
              </div>

              {/* Chart placeholder */}
              <div className="mt-6 rounded-lg border bg-muted/30 p-8">
                <div className="flex h-48 items-center justify-center">
                  <div className="text-center">
                    <div className="text-sm font-medium text-muted-foreground">
                      Hours Saved Trend
                    </div>
                    <div className="mt-4 flex items-end justify-center gap-1">
                      {[40, 55, 45, 60, 75, 65, 80, 85, 70, 90, 95, 100].map((height, i) => (
                        <div
                          key={i}
                          className="w-6 rounded-t bg-accent/80 transition-all hover:bg-accent"
                          style={{ height: `${height}%` }}
                        />
                      ))}
                    </div>
                    <div className="mt-2 flex justify-between text-xs text-muted-foreground">
                      <span>Jan</span>
                      <span>Jun</span>
                      <span>Dec</span>
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  )
}

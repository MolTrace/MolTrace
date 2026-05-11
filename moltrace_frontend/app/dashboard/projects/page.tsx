import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { FolderOpen, Plus, Users, Clock, FileText } from "lucide-react"

const projects = [
  {
    id: "API-2024-Q4",
    name: "API-2024-Q4-Development",
    description: "Q4 API compound development and characterization",
    status: "active",
    progress: 68,
    team: 5,
    analyses: 23,
    lastActivity: "2 hours ago",
  },
  {
    id: "MET-STUDY",
    name: "Metabolite Study Phase II",
    description: "Phase II metabolite identification and profiling",
    status: "active",
    progress: 45,
    team: 3,
    analyses: 15,
    lastActivity: "1 day ago",
  },
  {
    id: "PROC-OPT",
    name: "Process Optimization Batch 12",
    description: "Suzuki coupling optimization for scale-up",
    status: "active",
    progress: 82,
    team: 4,
    analyses: 34,
    lastActivity: "4 hours ago",
  },
  {
    id: "IMP-PROF",
    name: "Impurity Profiling Campaign",
    description: "ICH Q3A compliance impurity characterization",
    status: "review",
    progress: 95,
    team: 2,
    analyses: 12,
    lastActivity: "3 days ago",
  },
]

export default function ProjectsPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-teal)" }}
          >
            MolTrace · Dashboard · Projects
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Projects</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Cross-program project overview — sample counts, activity timelines, and quick links into spectroscopy, regulatory, and reaction workspaces.
          </p>
        </div>
        <Button className="gap-2">
          <Plus className="h-4 w-4" />
          New Project
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {projects.map((project) => (
          <Card key={project.id} className="cursor-pointer transition-shadow hover:shadow-md">
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-secondary">
                  <FolderOpen className="h-5 w-5" />
                </div>
                <Badge variant={project.status === "active" ? "default" : "secondary"}>
                  {project.status}
                </Badge>
              </div>
              <CardTitle className="mt-3 text-lg">{project.name}</CardTitle>
              <CardDescription>{project.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="mb-3">
                <div className="mb-1.5 flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Progress</span>
                  <span className="font-mono">{project.progress}%</span>
                </div>
                <Progress value={project.progress} className="h-1.5" />
              </div>
              <div className="flex items-center justify-between text-sm text-muted-foreground">
                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-1">
                    <Users className="h-3.5 w-3.5" />
                    {project.team}
                  </span>
                  <span className="flex items-center gap-1">
                    <FileText className="h-3.5 w-3.5" />
                    {project.analyses}
                  </span>
                </div>
                <span className="flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" />
                  {project.lastActivity}
                </span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}

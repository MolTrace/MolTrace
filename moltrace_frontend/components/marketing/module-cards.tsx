import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { FlaskConical, Scale } from "lucide-react"
import { SpectraCheckLogoIcon } from "@/components/branding/spectracheck-logo-icon"

const modules = [
  {
    icon: SpectraCheckLogoIcon,
    title: "Spectroscopy Intelligence",
    description: "NMR structure elucidation, LC-MS/MS unknown annotation, and multi-technique correlation with confidence scoring.",
    features: [
      "1D/2D NMR interpretation",
      "MS/MS fragmentation prediction",
      "LC-MS family grouping",
      "Peak-to-structure mapping",
    ],
    badge: "Most Popular",
  },
  {
    icon: Scale,
    title: "Regulatory Intelligence Hub",
    description: "Automated dossier assembly, requirement tracking, and evidence linking for global regulatory submissions.",
    features: [
      "ICH-compliant reports",
      "Jurisdiction mapping",
      "Change control tracking",
      "Audit trail export",
    ],
    badge: null,
  },
  {
    icon: FlaskConical,
    title: "Reaction Optimization",
    description: "Bayesian optimization of reaction conditions with uncertainty quantification and human-in-the-loop validation.",
    features: [
      "Multi-objective optimization",
      "Constraint handling",
      "Sensitivity analysis",
      "Batch experiment design",
    ],
    badge: null,
  },
]

export function ModuleCards() {
  return (
    <section className="py-24" id="platform">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="text-center">
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Three modules. One unified platform.
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-muted-foreground">
            Each module is purpose-built for scientific rigor, with transparent AI reasoning 
            and mandatory human oversight.
          </p>
        </div>
        <div className="mt-16 grid gap-8 lg:grid-cols-3">
          {modules.map((module) => (
            <Card key={module.title} className="relative flex flex-col">
              {module.badge && (
                <Badge className="absolute -top-3 left-6 px-3">{module.badge}</Badge>
              )}
              <CardHeader className="pb-4">
                <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-secondary">
                  <module.icon className="h-6 w-6" />
                </div>
                <CardTitle className="text-xl">{module.title}</CardTitle>
                <CardDescription className="text-base">{module.description}</CardDescription>
              </CardHeader>
              <CardContent className="flex-1">
                <ul className="space-y-2">
                  {module.features.map((feature) => (
                    <li key={feature} className="flex items-center gap-2 text-sm text-muted-foreground">
                      <div className="h-1.5 w-1.5 rounded-full bg-accent" />
                      {feature}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  )
}

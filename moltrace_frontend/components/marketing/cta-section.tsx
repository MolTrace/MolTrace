import { Button } from "@/components/ui/button"
import { ArrowRight, Play } from "lucide-react"
import Link from "next/link"

export function CTASection() {
  return (
    <section className="py-24" id="demo">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-2xl bg-foreground px-8 py-16 text-background sm:px-16 sm:py-20">
          <div className="scientific-grid-subtle absolute inset-0 opacity-10" />
          <div className="relative mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
              Ready to transform your analytical workflows?
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-lg text-background/80">
              See how MolTrace reduces your time-to-insight from days to minutes while maintaining the scientific rigor your work demands.
            </p>
            <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
              <Button
                size="lg"
                variant="secondary"
                className="min-w-[180px] gap-2 bg-background text-foreground hover:bg-background/90"
                asChild
              >
                <Link href="/contact?reason=Request%20a%20demo">
                  Request Demo
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button
                size="lg"
                variant="outline"
                className="min-w-[180px] gap-2 border-background/30 text-background hover:bg-background/10"
                asChild
              >
                <Link href="/dashboard">
                  <Play className="h-4 w-4" />
                  View Platform
                </Link>
              </Button>
            </div>
            <p className="mt-6 text-xs uppercase tracking-widest text-background/50">
              No credit card required &middot; 14-day free trial &middot; SOC 2-aligned
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}

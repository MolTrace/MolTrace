import type { ReactNode } from "react"
import { Footer } from "@/components/marketing/footer"
import { Header } from "@/components/marketing/header"

type AuthPageLayoutProps = {
  children: ReactNode
  title: string
  description?: string
}

export function AuthPageLayout({ children, title, description }: AuthPageLayoutProps) {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Header />
      <main className="flex flex-1 flex-col items-center justify-center px-4 py-12 sm:py-16">
        <div className="w-full max-w-md space-y-6">
          <div className="space-y-2 text-center">
            <h1 className="font-mono text-2xl font-bold tracking-tight">{title}</h1>
            {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
          </div>
          {children}
        </div>
      </main>
      <Footer />
    </div>
  )
}

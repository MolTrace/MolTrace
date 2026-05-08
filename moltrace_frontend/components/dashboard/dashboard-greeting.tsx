"use client"

function timeOfDayGreeting(now: Date): string {
  const hour = now.getHours()
  if (hour < 5) return "Working late"
  if (hour < 12) return "Good morning"
  if (hour < 18) return "Good afternoon"
  return "Good evening"
}

function nameFromEmail(email: string | null): string | null {
  if (!email) return null
  const localPart = email.split("@")[0] ?? ""
  if (!localPart) return null
  const cleaned = localPart.replace(/[._-]+/g, " ").trim()
  if (!cleaned) return null
  return cleaned
    .split(/\s+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ")
}

type DashboardGreetingProps = {
  email: string | null
  tenantName?: string | null
}

export function DashboardGreeting({ email, tenantName }: DashboardGreetingProps) {
  const greeting = timeOfDayGreeting(new Date())
  const name = nameFromEmail(email)
  const headline = name ? `${greeting}, ${name}` : greeting

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">{headline}</h1>
      <p className="text-muted-foreground">
        {tenantName
          ? `Here's what's happening across ${tenantName} today.`
          : "Here's what's happening across your workflows today."}
      </p>
    </div>
  )
}

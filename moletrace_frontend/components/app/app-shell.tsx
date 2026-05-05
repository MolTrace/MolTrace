import { ResponsiveAppShell } from "@/src/components/app-shell/ResponsiveAppShell"

export function AppShell({ children }: { children: React.ReactNode }) {
  return <ResponsiveAppShell>{children}</ResponsiveAppShell>
}

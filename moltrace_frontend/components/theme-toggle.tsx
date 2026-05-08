"use client"

import * as React from "react"
import { Moon, Sun } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useTheme } from "@/components/theme-provider"
import { cn } from "@/lib/utils"

export function ThemeToggle() {
  const { setTheme, resolvedTheme, theme } = useTheme()
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  const currentTheme = resolvedTheme || theme || "light"
  const isDark = mounted && currentTheme === "dark"

  return (
    <Button
      variant="ghost"
      size="icon"
      className="relative shrink-0"
      onClick={() => {
        if (!mounted) return
        setTheme(isDark ? "light" : "dark")
      }}
      aria-label={mounted ? `Switch to ${isDark ? "light" : "dark"} mode` : "Toggle theme"}
    >
      {!mounted ? (
        <Sun className="h-4 w-4 text-muted-foreground" aria-hidden />
      ) : (
        <>
          <Sun
            className={cn(
              "h-4 w-4 rotate-0 scale-100 transition-all",
              isDark && "-rotate-90 scale-0",
            )}
            aria-hidden
          />
          <Moon
            className={cn(
              "absolute h-4 w-4 transition-all",
              isDark ? "rotate-0 scale-100" : "rotate-90 scale-0",
            )}
            aria-hidden
          />
        </>
      )}
      <span className="sr-only">Toggle theme</span>
    </Button>
  )
}

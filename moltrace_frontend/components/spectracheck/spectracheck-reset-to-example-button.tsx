"use client"

import { RotateCcw } from "lucide-react"

import { Button } from "@/components/ui/button"

/**
 * Tiny conditional reset-to-default affordance used across the session
 * inputs on the "NMR text & candidate structures" tab.
 *
 * Visibility rule:
 *   - The button renders only when ``current.trim() !== fallback.trim()``.
 *   - When the field still holds the bundled example, the button stays
 *     hidden so the UI doesn't read as cluttered.
 *
 * This is the parity behaviour the user asked for: 1H NMR text + 13C text
 * + Candidate structures all get the same affordance, so a user who has
 * cleared / overwritten / cross-tab-linked any field can recover the
 * original example without reloading the page.
 */
export function ResetToExampleButton({
  current,
  fallback,
  onReset,
  testId,
  title = "Restore the bundled example value",
  label = "Reset to example",
}: {
  current: string
  fallback: string
  onReset: () => void
  testId: string
  title?: string
  label?: string
}) {
  if (current.trim() === fallback.trim()) return null
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="h-6 px-2 font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
      style={{ color: "var(--mt-amber)" }}
      onClick={onReset}
      data-testid={testId}
      title={title}
    >
      <RotateCcw className="mr-1 h-3 w-3" aria-hidden />
      {label}
    </Button>
  )
}

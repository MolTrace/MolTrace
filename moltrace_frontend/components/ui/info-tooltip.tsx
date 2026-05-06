"use client"

import { Info } from "lucide-react"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

export type InfoTooltipProps = {
  content: string
  className?: string
  /** Short accessible name for the trigger control */
  label?: string
}

export function InfoTooltip({ content, className, label = "More information" }: InfoTooltipProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex size-5 shrink-0 items-center justify-center rounded-full text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            className,
          )}
          aria-label={label}
        >
          <Info className="size-3.5" aria-hidden strokeWidth={2} />
        </button>
      </TooltipTrigger>
      <TooltipContent sideOffset={4} className="max-w-xs text-xs">
        {content}
      </TooltipContent>
    </Tooltip>
  )
}

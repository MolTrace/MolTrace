"use client"

import { cn } from "@/lib/utils"

export type StatusFilterOption<T extends string> = {
  value: T
  label: string
  count?: number
}

type Props<T extends string> = {
  value: T
  onChange: (value: T) => void
  options: StatusFilterOption<T>[]
  label?: string
}

export function StatusFilterPills<T extends string>({
  value,
  onChange,
  options,
  label = "Filter by status",
}: Props<T>) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={label}>
      {options.map((opt) => {
        const active = opt.value === value
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            aria-pressed={active}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
              active
                ? "border-foreground bg-foreground text-background"
                : "border-border bg-background text-muted-foreground hover:border-foreground/40 hover:bg-muted",
            )}
          >
            <span>{opt.label}</span>
            {opt.count != null ? (
              <span className={cn("tabular-nums", active ? "opacity-80" : "opacity-70")}>
                {opt.count}
              </span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}

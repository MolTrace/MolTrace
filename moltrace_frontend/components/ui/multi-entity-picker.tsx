"use client"

import { useEffect, useMemo, useState } from "react"
import { Check, ChevronsUpDown, Loader2, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import type { EntityOption } from "@/components/ui/entity-picker"

type MultiEntityPickerProps = {
  value: (number | string)[]
  onChange: (ids: (number | string)[]) => void
  options?: EntityOption[]
  load?: () => Promise<EntityOption[]>
  placeholder?: string
  searchPlaceholder?: string
  emptyText?: string
  disabled?: boolean
  id?: string
  ariaLabel?: string
  className?: string
}

/** Multi-select object picker — replaces "paste a JSON array of ids" textareas.
 *  Shows the chosen entities as removable chips; returns the id array. */
export function MultiEntityPicker({
  value,
  onChange,
  options,
  load,
  placeholder = "Select…",
  searchPlaceholder = "Search…",
  emptyText = "No matches.",
  disabled,
  id,
  ariaLabel,
  className,
}: MultiEntityPickerProps) {
  const [open, setOpen] = useState(false)
  const [loaded, setLoaded] = useState<EntityOption[] | null>(options ?? null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (options) setLoaded(options)
  }, [options])

  // Eager-load when there's already a value (to resolve chip labels) or on open.
  useEffect(() => {
    if (options || loaded != null || !load) return
    if (!open && value.length === 0) return
    let cancelled = false
    setLoading(true)
    setError(false)
    void load()
      .then((opts) => {
        if (!cancelled) setLoaded(opts)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, load, options, loaded, value.length])

  const items = loaded ?? []
  const selectedSet = useMemo(() => new Set(value.map(String)), [value])
  const labelFor = (entityId: number | string) =>
    items.find((o) => String(o.id) === String(entityId))?.label ?? `#${entityId}`

  function toggle(entityId: number | string) {
    if (selectedSet.has(String(entityId))) {
      onChange(value.filter((v) => String(v) !== String(entityId)))
    } else {
      onChange([...value, entityId])
    }
  }

  return (
    <div className={className}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            id={id}
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            aria-label={ariaLabel}
            disabled={disabled}
            className={cn("w-full justify-between font-normal", value.length === 0 && "text-muted-foreground")}
          >
            <span className="truncate">{value.length ? `${value.length} selected` : placeholder}</span>
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" aria-hidden />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
          <Command>
            <CommandInput placeholder={searchPlaceholder} />
            <CommandList>
              {loading ? (
                <div className="flex items-center justify-center gap-2 py-6 text-xs text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> Loading…
                </div>
              ) : error ? (
                <div className="py-6 text-center text-xs text-destructive">Could not load options.</div>
              ) : (
                <>
                  <CommandEmpty>{emptyText}</CommandEmpty>
                  <CommandGroup>
                    {items.map((o) => {
                      const checked = selectedSet.has(String(o.id))
                      return (
                        <CommandItem
                          key={String(o.id)}
                          value={`${o.label} ${o.description ?? ""} ${o.id}`}
                          onSelect={() => toggle(o.id)}
                        >
                          <Check className={cn("mr-2 h-4 w-4 shrink-0", checked ? "opacity-100" : "opacity-0")} aria-hidden />
                          <span className="flex min-w-0 flex-col">
                            <span className="truncate">{o.label}</span>
                            {o.description ? (
                              <span className="truncate text-[11px] text-muted-foreground">{o.description}</span>
                            ) : null}
                          </span>
                        </CommandItem>
                      )
                    })}
                  </CommandGroup>
                </>
              )}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {value.length ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {value.map((entityId) => (
            <span
              key={String(entityId)}
              className="inline-flex items-center gap-1 rounded-md border border-border bg-muted/50 px-2 py-0.5 text-xs"
            >
              <span className="truncate">{labelFor(entityId)}</span>
              <button
                type="button"
                aria-label={`Remove ${labelFor(entityId)}`}
                className="text-muted-foreground hover:text-foreground"
                onClick={() => toggle(entityId)}
              >
                <X className="h-3 w-3" aria-hidden />
              </button>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  )
}

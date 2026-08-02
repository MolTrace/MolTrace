"use client"

import { useEffect, useMemo, useState } from "react"
import { Check, ChevronsUpDown, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { ApiError } from "@/lib/api/client"
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

export type EntityOption = { id: number | string; label: string; description?: string }

type EntityPickerProps = {
  value: number | string | null | undefined
  onChange: (id: number | string | null) => void
  /** Sync options, or use `load` for lazy fetch on first open. */
  options?: EntityOption[]
  load?: () => Promise<EntityOption[]>
  placeholder?: string
  searchPlaceholder?: string
  emptyText?: string
  disabled?: boolean
  allowClear?: boolean
  id?: string
  ariaLabel?: string
  className?: string
}

/**
 * A searchable object picker — the standard replacement for "type a raw integer
 * id / foreign key" inputs. Returns the selected entity's id; never makes the
 * user know it. Pass `options` when the parent already has the list, or `load`
 * to lazily fetch on first open.
 */

/** Turns a failed load into something a reader can act on. */
function describeLoadFailure(err: unknown): string {
  if (err instanceof ApiError) {
    // A licensing refusal is not a permission failure — one is an upgrade path,
    // the other is an access error, and they must not read the same.
    if (err.moduleNotIncluded) return "This list belongs to a product this workspace does not include."
    if (err.status === 401 || err.status === 403) return "Sign in to load these options."
    if (err.status === 404) return "That list is not available here."
    if (err.status >= 500) return "The service could not be reached. Try again shortly."
  }
  return "Could not load options."
}

export function EntityPicker({
  value,
  onChange,
  options,
  load,
  placeholder = "Select…",
  searchPlaceholder = "Search…",
  emptyText = "No matches.",
  disabled,
  allowClear,
  id,
  ariaLabel,
  className,
}: EntityPickerProps) {
  const [open, setOpen] = useState(false)
  const [loaded, setLoaded] = useState<EntityOption[] | null>(options ?? null)
  const [loading, setLoading] = useState(false)
  // The REASON, not a boolean. "Could not load options." is the same sentence
  // whether you are signed out, offline, or looking at a list this deployment
  // does not serve — and only one of those is something you can act on.
  const [error, setError] = useState("")

  useEffect(() => {
    if (options) setLoaded(options)
  }, [options])

  // Lazy-load once, the first time the picker opens.
  useEffect(() => {
    if (!open || options || loaded != null || !load) return
    let cancelled = false
    setLoading(true)
    setError("")
    void load()
      .then((opts) => {
        if (!cancelled) setLoaded(opts)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(describeLoadFailure(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, load, options, loaded])

  const items = loaded ?? []
  const selected = useMemo(
    () => items.find((o) => String(o.id) === String(value)) ?? null,
    [items, value],
  )
  const hasValue = value != null && value !== ""
  const triggerLabel = selected ? selected.label : hasValue ? `#${value}` : ""

  return (
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
          className={cn("w-full justify-between font-normal", !selected && !hasValue && "text-muted-foreground", className)}
        >
          <span className="truncate">{triggerLabel || placeholder}</span>
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
              <div className="px-3 py-6 text-center text-xs text-destructive">{error}</div>
            ) : (
              <>
                <CommandEmpty>{emptyText}</CommandEmpty>
                <CommandGroup>
                  {allowClear && hasValue ? (
                    <CommandItem
                      value="__clear__"
                      onSelect={() => {
                        onChange(null)
                        setOpen(false)
                      }}
                      className="text-muted-foreground"
                    >
                      Clear selection
                    </CommandItem>
                  ) : null}
                  {items.map((o) => (
                    <CommandItem
                      key={String(o.id)}
                      value={`${o.label} ${o.description ?? ""} ${o.id}`}
                      onSelect={() => {
                        onChange(o.id)
                        setOpen(false)
                      }}
                    >
                      <Check
                        className={cn("mr-2 h-4 w-4 shrink-0", String(o.id) === String(value) ? "opacity-100" : "opacity-0")}
                        aria-hidden
                      />
                      <span className="flex min-w-0 flex-col">
                        <span className="truncate">{o.label}</span>
                        {o.description ? (
                          <span className="truncate text-[11px] text-muted-foreground">{o.description}</span>
                        ) : null}
                      </span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

"use client"

import { useState } from "react"
import { Plus, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

/**
 * Edit a flat list of scalars (numbers or short strings) as removable chips
 * instead of hand-authoring a raw JSON array. Emits the array; the wire contract
 * (e.g. `linked_requirement_ids_json: [1, 4, 9]`) is unchanged.
 *
 * For id-lists this is the no-backend half of the "raw array → picker" upgrade:
 * a named MultiEntityPicker needs a list endpoint, but typed-number chips do not.
 *
 * Seeds from `initialValue` on mount; reset by bumping the React `key`.
 */
export function ScalarListField({
  label,
  onChange,
  initialValue = [],
  valueType = "number",
  placeholder,
  addLabel = "Add",
  description,
  idPrefix = "scalar-list",
  dedupe = true,
}: {
  label: string
  onChange: (next: (number | string)[]) => void
  initialValue?: (number | string)[]
  valueType?: "number" | "text"
  placeholder?: string
  addLabel?: string
  description?: string
  idPrefix?: string
  dedupe?: boolean
}) {
  const [items, setItems] = useState<(number | string)[]>(() => initialValue)
  const [draft, setDraft] = useState("")
  const [err, setErr] = useState("")

  function commit(next: (number | string)[]) {
    setItems(next)
    onChange(next)
  }

  function add() {
    const raw = draft.trim()
    if (!raw) return
    let value: number | string
    if (valueType === "number") {
      const n = Number(raw)
      if (!Number.isFinite(n)) {
        setErr("Enter a number.")
        return
      }
      value = n
    } else {
      value = raw
    }
    if (dedupe && items.some((it) => it === value)) {
      setErr("Already added.")
      setDraft("")
      return
    }
    setErr("")
    setDraft("")
    commit([...items, value])
  }

  function remove(index: number) {
    commit(items.filter((_, i) => i !== index))
  }

  const inputId = `${idPrefix}-input`

  return (
    <div className="space-y-1.5">
      <Label htmlFor={inputId}>{label}</Label>
      {description ? <p className="text-[11px] text-muted-foreground">{description}</p> : null}
      <div className="flex items-center gap-2">
        <Input
          id={inputId}
          value={draft}
          placeholder={placeholder ?? (valueType === "number" ? "Add an ID…" : "Add…")}
          inputMode={valueType === "number" ? "numeric" : undefined}
          onChange={(e) => {
            setDraft(e.target.value)
            if (err) setErr("")
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault()
              add()
            }
          }}
        />
        <Button type="button" variant="outline" size="sm" className="gap-1.5 shrink-0" onClick={add}>
          <Plus className="h-3.5 w-3.5" />
          {addLabel}
        </Button>
      </div>
      {err ? <p className="text-[11px] text-destructive">{err}</p> : null}
      {items.length > 0 ? (
        <div className="flex flex-wrap gap-1.5 pt-0.5">
          {items.map((it, i) => (
            <Badge key={`${it}-${i}`} variant="secondary" className="gap-1 pr-1 font-mono">
              {String(it)}
              <button
                type="button"
                aria-label={`Remove ${String(it)}`}
                className="ml-0.5 rounded-sm opacity-70 hover:opacity-100"
                onClick={() => remove(i)}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      ) : null}
    </div>
  )
}

"use client"

import { useMemo, useState } from "react"
import { Plus, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

/**
 * Structured editor for a flat JSON object.
 *
 * Replaces "paste raw JSON into a <Textarea>" create-form inputs: scientists
 * fill labeled fields (and optionally add their own key/value rows) and the
 * component assembles the object. The wire contract is unchanged — the parent
 * still sends a JSON object — but no one has to hand-author braces.
 *
 * Design notes:
 * - Number fields keep a raw-text DRAFT so decimals type smoothly ("0." → "0.95")
 *   while the emitted value is coerced to a number.
 * - Empty fields/rows are OMITTED from the emitted object (an all-empty editor
 *   emits {}), matching the old "empty textarea → {}" behavior.
 * - The component seeds its drafts from `initialValue` ONCE on mount and is
 *   otherwise self-stateful; reset it by bumping its React `key` (the parent's
 *   create forms do exactly this after a successful submit).
 */

export type StructuredJsonFieldType = "text" | "number" | "textarea"

export type StructuredJsonField = {
  key: string
  label: string
  type?: StructuredJsonFieldType
  placeholder?: string
  help?: string
}

type CustomRow = { id: number; key: string; value: string }

export type JsonValueType = "text" | "number" | "auto"

function coerce(raw: string, valueType: JsonValueType): unknown | undefined {
  const trimmed = raw.trim()
  if (trimmed === "") return undefined
  if (valueType === "text") return raw
  if (valueType === "number") {
    const n = Number(trimmed)
    return Number.isFinite(n) ? n : undefined
  }
  // "auto": detect number / boolean / null, else keep the raw string. Only
  // coerce to a number when it round-trips losslessly (String(n) === input), so
  // identifier-like values keep their exact text — "007" stays "007", "1e3"
  // stays "1e3", "0.50" keeps its trailing zero — while "98.5" becomes a number.
  if (/^[+-]?(\d|\.)/.test(trimmed)) {
    const n = Number(trimmed)
    if (Number.isFinite(n) && String(n) === trimmed) return n
  }
  if (trimmed === "true") return true
  if (trimmed === "false") return false
  if (trimmed === "null") return null
  return raw
}

export function StructuredJsonObjectEditor({
  fields = [],
  initialValue = {},
  onChange,
  allowCustomKeys = false,
  customValueType = "text",
  addLabel = "Add field",
  keyPlaceholder = "key",
  valuePlaceholder = "value",
  idPrefix = "sje",
  description,
}: {
  fields?: StructuredJsonField[]
  initialValue?: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
  allowCustomKeys?: boolean
  customValueType?: JsonValueType
  addLabel?: string
  keyPlaceholder?: string
  valuePlaceholder?: string
  idPrefix?: string
  description?: string
}) {
  const fieldKeys = useMemo(() => new Set(fields.map((f) => f.key)), [fields])

  // Raw-text drafts for the known fields, seeded once from initialValue.
  const [drafts, setDrafts] = useState<Record<string, string>>(() => {
    const seed: Record<string, string> = {}
    for (const f of fields) {
      const v = initialValue[f.key]
      seed[f.key] = v == null ? "" : String(v)
    }
    return seed
  })

  // Free-form rows for keys outside the known field set, seeded from initialValue.
  const [rows, setRows] = useState<CustomRow[]>(() => {
    if (!allowCustomKeys) return []
    let id = 0
    return Object.entries(initialValue)
      .filter(([k]) => !fieldKeys.has(k))
      .map(([k, v]) => ({ id: id++, key: k, value: v == null ? "" : String(v) }))
  })
  const [nextRowId, setNextRowId] = useState(() => 10_000)

  function assemble(nextDrafts: Record<string, string>, nextRows: CustomRow[]): Record<string, unknown> {
    const obj: Record<string, unknown> = {}
    for (const f of fields) {
      const v = coerce(nextDrafts[f.key] ?? "", f.type === "number" ? "number" : "text")
      if (v !== undefined) obj[f.key] = v
    }
    for (const row of nextRows) {
      const key = row.key.trim()
      if (!key) continue
      const v = coerce(row.value, customValueType)
      if (v !== undefined) obj[key] = v
    }
    return obj
  }

  function updateField(key: string, raw: string) {
    const nextDrafts = { ...drafts, [key]: raw }
    setDrafts(nextDrafts)
    onChange(assemble(nextDrafts, rows))
  }

  function updateRow(id: number, patch: Partial<Pick<CustomRow, "key" | "value">>) {
    const nextRows = rows.map((r) => (r.id === id ? { ...r, ...patch } : r))
    setRows(nextRows)
    onChange(assemble(drafts, nextRows))
  }

  function addRow() {
    setRows((prev) => [...prev, { id: nextRowId, key: "", value: "" }])
    setNextRowId((n) => n + 1)
  }

  function removeRow(id: number) {
    const nextRows = rows.filter((r) => r.id !== id)
    setRows(nextRows)
    onChange(assemble(drafts, nextRows))
  }

  return (
    <div className="space-y-3 rounded-lg border bg-muted/20 p-3">
      {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}

      {fields.map((f) => {
        const id = `${idPrefix}-${f.key}`
        return (
          <div key={f.key} className="space-y-1">
            <Label htmlFor={id} className="text-xs font-medium">
              {f.label}
            </Label>
            {f.type === "textarea" ? (
              <Textarea
                id={id}
                value={drafts[f.key] ?? ""}
                placeholder={f.placeholder}
                onChange={(e) => updateField(f.key, e.target.value)}
                rows={3}
              />
            ) : (
              <Input
                id={id}
                value={drafts[f.key] ?? ""}
                placeholder={f.placeholder}
                inputMode={f.type === "number" ? "decimal" : undefined}
                onChange={(e) => updateField(f.key, e.target.value)}
              />
            )}
            {f.help ? <p className="text-[11px] text-muted-foreground">{f.help}</p> : null}
          </div>
        )
      })}

      {allowCustomKeys ? (
        <div className="space-y-2">
          {rows.length > 0 ? (
            <div className="space-y-2">
              {rows.map((row) => (
                <div key={row.id} className="flex items-center gap-2">
                  <Input
                    aria-label={`${keyPlaceholder} (row ${row.id})`}
                    className="flex-1"
                    value={row.key}
                    placeholder={keyPlaceholder}
                    onChange={(e) => updateRow(row.id, { key: e.target.value })}
                  />
                  <Input
                    aria-label={`${valuePlaceholder} (row ${row.id})`}
                    className="flex-1"
                    value={row.value}
                    placeholder={valuePlaceholder}
                    inputMode={customValueType === "number" ? "decimal" : undefined}
                    onChange={(e) => updateRow(row.id, { value: e.target.value })}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label="Remove field"
                    onClick={() => removeRow(row.id)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          ) : null}
          <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={addRow}>
            <Plus className="h-3.5 w-3.5" />
            {addLabel}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

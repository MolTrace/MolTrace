"use client"

import { useState } from "react"
import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { JsonObjectField } from "@/components/ui/json-object-field"
import type { StructuredJsonField } from "@/components/ui/structured-json-editor"

/**
 * Edit a JSON array-of-objects (e.g. test-case `steps_json`) as a list of
 * structured rows instead of a hand-authored raw JSON array. Each row is a
 * {@link JsonObjectField} (structured fields + a raw-JSON escape hatch), so
 * arbitrary / nested step shapes are preserved. Emits the array of non-empty
 * row objects; the wire contract is unchanged.
 *
 * Seeds from `initialValue` on mount; reset by bumping the React `key`.
 */
export function ObjectArrayField({
  label,
  onChange,
  initialValue = [],
  itemLabel = "Item",
  addLabel = "Add item",
  fields = [],
  description,
  idPrefix = "object-array",
}: {
  label: string
  onChange: (next: Record<string, unknown>[]) => void
  initialValue?: Record<string, unknown>[]
  itemLabel?: string
  addLabel?: string
  fields?: StructuredJsonField[]
  description?: string
  idPrefix?: string
}) {
  // Each row keeps a stable id (for React keys / removal) and its current object.
  const [rows, setRows] = useState<{ id: number; obj: Record<string, unknown> }[]>(() =>
    initialValue.map((obj, i) => ({ id: i, obj })),
  )
  const [nextId, setNextId] = useState(() => initialValue.length + 1000)

  function emit(next: { id: number; obj: Record<string, unknown> }[]) {
    onChange(next.map((r) => r.obj).filter((o) => Object.keys(o).length > 0))
  }

  function updateRow(id: number, obj: Record<string, unknown>) {
    const next = rows.map((r) => (r.id === id ? { ...r, obj } : r))
    setRows(next)
    emit(next)
  }

  function addRow() {
    setRows((prev) => [...prev, { id: nextId, obj: {} }])
    setNextId((n) => n + 1)
  }

  function removeRow(id: number) {
    const next = rows.filter((r) => r.id !== id)
    setRows(next)
    emit(next)
  }

  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {description ? <p className="text-[11px] text-muted-foreground">{description}</p> : null}

      {rows.length > 0 ? (
        <div className="space-y-3">
          {rows.map((row, i) => (
            <div key={row.id} className="rounded-lg border bg-muted/10 p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">
                  {itemLabel} {i + 1}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  aria-label={`Remove ${itemLabel} ${i + 1}`}
                  onClick={() => removeRow(row.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
              <JsonObjectField
                idPrefix={`${idPrefix}-${row.id}`}
                label={`${itemLabel} ${i + 1} details`}
                fields={fields}
                customValueType="auto"
                onChange={(obj) => updateRow(row.id, obj)}
              />
            </div>
          ))}
        </div>
      ) : null}

      <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={addRow}>
        <Plus className="h-3.5 w-3.5" />
        {addLabel}
      </Button>
    </div>
  )
}

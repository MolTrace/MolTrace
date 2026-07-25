"use client"

import { useState } from "react"
import { Braces, ListPlus, Plus, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

/**
 * A labeled list-of-numbers editor for `[1, 2, ...]` wire arrays — record-id
 * references (evidence items, validation records, citations) that the backend
 * stores as `list[int]`. One numeric input per row plus a raw-JSON escape hatch.
 *
 * Emits a plain number[] on every change (blank/non-numeric rows omitted; an
 * all-empty list emits []). Seeds from `initialValue` ONCE on mount; reset via a
 * React `key` bump. Mirrors StringListField for the string case.
 */
export function NumberListField({
  label,
  onChange,
  initialValue = [],
  itemLabel = "ID",
  itemPlaceholder = "e.g. 42",
  addLabel = "Add ID",
  description,
}: {
  label: string
  onChange: (next: number[]) => void
  initialValue?: unknown[]
  itemLabel?: string
  itemPlaceholder?: string
  addLabel?: string
  description?: string
  idPrefix?: string
}) {
  type Row = { id: number; value: string }

  const [rows, setRows] = useState<Row[]>(() =>
    initialValue
      .filter((v) => v != null && v !== "")
      .map((v, i) => ({ id: i, value: String(v) })),
  )
  const [nextId, setNextId] = useState(() => 10_000)
  const [mode, setMode] = useState<"list" | "raw">("list")
  const [rawDraft, setRawDraft] = useState("")
  const [rawError, setRawError] = useState("")

  function assemble(nextRows: Row[]): number[] {
    const out: number[] = []
    for (const r of nextRows) {
      const t = r.value.trim()
      if (t === "") continue
      const n = Number(t)
      if (Number.isFinite(n)) out.push(n)
    }
    return out
  }

  function updateRow(id: number, value: string) {
    const next = rows.map((r) => (r.id === id ? { ...r, value } : r))
    setRows(next)
    onChange(assemble(next))
  }

  function addRow() {
    setRows((prev) => [...prev, { id: nextId, value: "" }])
    setNextId((n) => n + 1)
  }

  function removeRow(id: number) {
    const next = rows.filter((r) => r.id !== id)
    setRows(next)
    onChange(assemble(next))
  }

  function enterRaw() {
    const list = assemble(rows)
    setRawDraft(list.length ? JSON.stringify(list) : "")
    setRawError("")
    setMode("raw")
  }

  function enterList() {
    const trimmed = rawDraft.trim()
    if (!trimmed) {
      // The raw box was cleared (onRawChange already emitted []). Clear the rows to match,
      // so the displayed list can't disagree with the emitted value.
      setRows([])
      onChange([])
    } else if (!rawError) {
      try {
        const parsed = JSON.parse(trimmed) as unknown[]
        let id = nextId
        setRows(
          parsed.filter((v) => v != null && v !== "").map((v) => ({ id: id++, value: String(v) })),
        )
        setNextId(id)
      } catch {
        /* keep existing rows */
      }
    }
    setRawError("")
    setMode("list")
  }

  function onRawChange(text: string) {
    setRawDraft(text)
    const trimmed = text.trim()
    if (!trimmed) {
      setRawError("")
      onChange([])
      return
    }
    let parsed: unknown
    try {
      parsed = JSON.parse(trimmed)
    } catch {
      setRawError("Enter valid JSON, or switch back to the list.")
      return
    }
    if (!Array.isArray(parsed)) {
      setRawError("Must be a JSON array of numbers (e.g. [12, 47]).")
      return
    }
    const out: number[] = []
    for (const v of parsed) {
      const n = typeof v === "number" ? v : Number(v)
      if (!Number.isFinite(n)) {
        setRawError(`"${String(v)}" is not a number.`)
        return
      }
      out.push(n)
    }
    setRawError("")
    onChange(out)
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <Label>{label}</Label>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 gap-1.5 text-xs text-muted-foreground"
          onClick={mode === "list" ? enterRaw : enterList}
        >
          {mode === "list" ? (
            <>
              <Braces className="h-3.5 w-3.5" />
              Edit as JSON
            </>
          ) : (
            <>
              <ListPlus className="h-3.5 w-3.5" />
              Use list
            </>
          )}
        </Button>
      </div>

      {mode === "list" ? (
        <div className="space-y-2 rounded-lg border bg-muted/20 p-3">
          {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}

          {rows.length > 0 ? (
            <div className="space-y-2">
              {rows.map((row) => (
                <div key={row.id} className="flex items-center gap-2">
                  <Input
                    aria-label={`${itemLabel} (row)`}
                    inputMode="numeric"
                    value={row.value}
                    placeholder={itemPlaceholder}
                    onChange={(e) => updateRow(row.id, e.target.value)}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={`Remove ${row.value.trim() || "row"}`}
                    onClick={() => removeRow(row.id)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              No entries yet. {addLabel ? `Use “${addLabel}” to start.` : ""}
            </p>
          )}

          <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={addRow}>
            <Plus className="h-3.5 w-3.5" />
            {addLabel}
          </Button>
        </div>
      ) : (
        <div className="space-y-1">
          <Textarea
            aria-label={`${label} (raw JSON)`}
            className="min-h-[80px] font-mono text-xs"
            value={rawDraft}
            spellCheck={false}
            placeholder="[]"
            onChange={(e) => onRawChange(e.target.value)}
          />
          {rawError ? (
            <p className="text-[11px] text-destructive">{rawError}</p>
          ) : description ? (
            <p className="text-[11px] text-muted-foreground">{description}</p>
          ) : null}
        </div>
      )}
    </div>
  )
}

"use client"

import { useId, useState } from "react"
import { Braces, Plus, Table2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

/**
 * A labeled name→choice table for flat `{"name": "<one of a fixed set>"}` wire
 * maps — e.g. optimization directions where each metric is "higher" or "lower".
 * The value column is a Select constrained to the allowed options, so a chemist
 * can't type a value the backend silently ignores. A raw-JSON escape hatch
 * covers paste-in / power users.
 *
 * Emits a plain `{name: choice}` object (incomplete rows omitted). Seeds ONCE
 * on mount; reset via a React `key` bump.
 */
export type ChoiceOption = { value: string; label: string }

export function KeyChoiceTableField({
  label,
  onChange,
  options,
  initialValue = {},
  keyLabel = "Name",
  valueLabel = "Choice",
  keyPlaceholder,
  addLabel = "Add row",
  suggestions = [],
  suggestionsHint,
  description,
  idPrefix = "kct",
}: {
  label: string
  onChange: (next: Record<string, string>) => void
  options: ChoiceOption[]
  initialValue?: Record<string, unknown>
  keyLabel?: string
  valueLabel?: string
  keyPlaceholder?: string
  addLabel?: string
  suggestions?: string[]
  suggestionsHint?: string
  description?: string
  idPrefix?: string
}) {
  type Row = { id: number; key: string; value: string }
  const optionValues = new Set(options.map((o) => o.value))
  const reactId = useId()
  const listId = `${idPrefix}-${reactId}-suggestions`

  const [rows, setRows] = useState<Row[]>(() => {
    let id = 0
    return Object.entries(initialValue)
      .filter(([, v]) => v != null)
      .map(([k, v]) => ({ id: id++, key: k, value: String(v) }))
  })
  const [nextId, setNextId] = useState(() => 10_000)
  const [mode, setMode] = useState<"table" | "raw">("table")
  const [rawDraft, setRawDraft] = useState("")
  const [rawError, setRawError] = useState("")

  function assemble(nextRows: Row[]): Record<string, string> {
    const obj: Record<string, string> = {}
    for (const row of nextRows) {
      const key = row.key.trim()
      if (!key || !optionValues.has(row.value)) continue
      obj[key] = row.value
    }
    return obj
  }

  function updateRow(id: number, patch: Partial<Pick<Row, "key" | "value">>) {
    const next = rows.map((r) => (r.id === id ? { ...r, ...patch } : r))
    setRows(next)
    onChange(assemble(next))
  }

  function addRow() {
    setRows((prev) => [...prev, { id: nextId, key: "", value: "" }])
    setNextId((n) => n + 1)
  }

  function removeRow(id: number) {
    const next = rows.filter((r) => r.id !== id)
    setRows(next)
    onChange(assemble(next))
  }

  function enterRaw() {
    const obj = assemble(rows)
    setRawDraft(Object.keys(obj).length ? JSON.stringify(obj, null, 2) : "")
    setRawError("")
    setMode("raw")
  }

  function enterTable() {
    const trimmed = rawDraft.trim()
    if (!trimmed) {
      // The raw box was cleared (onRawChange already emitted {}). Clear the rows to match.
      setRows([])
      onChange({})
    } else if (!rawError) {
      try {
        const parsed = JSON.parse(trimmed) as Record<string, unknown>
        let id = nextId
        setRows(
          Object.entries(parsed)
            .filter(([, v]) => v != null)
            .map(([k, v]) => ({ id: id++, key: k, value: String(v) })),
        )
        setNextId(id)
      } catch {
        /* keep existing rows */
      }
    }
    setRawError("")
    setMode("table")
  }

  function onRawChange(text: string) {
    setRawDraft(text)
    const trimmed = text.trim()
    if (!trimmed) {
      setRawError("")
      onChange({})
      return
    }
    let parsed: unknown
    try {
      parsed = JSON.parse(trimmed)
    } catch {
      setRawError("Enter valid JSON, or switch back to the table.")
      return
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      setRawError("Must be a JSON object.")
      return
    }
    const allowed = options.map((o) => o.value)
    const obj: Record<string, string> = {}
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      const s = String(v)
      if (!allowed.includes(s)) {
        setRawError(`"${k}" must be one of: ${allowed.join(", ")}.`)
        return
      }
      obj[k] = s
    }
    setRawError("")
    onChange(obj)
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
          onClick={mode === "table" ? enterRaw : enterTable}
        >
          {mode === "table" ? (
            <>
              <Braces className="h-3.5 w-3.5" />
              Edit as JSON
            </>
          ) : (
            <>
              <Table2 className="h-3.5 w-3.5" />
              Use table
            </>
          )}
        </Button>
      </div>

      {mode === "table" ? (
        <div className="space-y-2 rounded-lg border bg-muted/20 p-3">
          {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}

          {rows.length > 0 ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2 pr-10 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                <span className="flex-[3]">{keyLabel}</span>
                <span className="flex-[2]">{valueLabel}</span>
              </div>
              {rows.map((row) => (
                <div key={row.id} className="flex items-center gap-2">
                  <div className="flex-[3]">
                    <Input
                      aria-label={`${keyLabel} (row)`}
                      list={suggestions.length ? listId : undefined}
                      value={row.key}
                      placeholder={keyPlaceholder ?? keyLabel}
                      onChange={(e) => updateRow(row.id, { key: e.target.value })}
                    />
                  </div>
                  <div className="flex-[2]">
                    <Select
                      value={row.value || undefined}
                      onValueChange={(v) => updateRow(row.id, { value: v })}
                    >
                      <SelectTrigger aria-label={`${valueLabel} (row)`}>
                        <SelectValue placeholder="Select…" />
                      </SelectTrigger>
                      <SelectContent>
                        {options.map((o) => (
                          <SelectItem key={o.value} value={o.value}>
                            {o.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={`Remove ${row.key.trim() || "row"}`}
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

          {suggestions.length > 0 ? (
            <>
              <datalist id={listId}>
                {suggestions.map((s) => (
                  <option key={s} value={s} />
                ))}
              </datalist>
              {suggestionsHint ? (
                <p className="text-[11px] text-muted-foreground">{suggestionsHint}</p>
              ) : null}
            </>
          ) : null}
        </div>
      ) : (
        <div className="space-y-1">
          <Textarea
            aria-label={`${label} (raw JSON)`}
            className="min-h-[100px] font-mono text-xs"
            value={rawDraft}
            spellCheck={false}
            placeholder="{}"
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

"use client"

import { useId, useMemo, useState } from "react"
import { Braces, Plus, Table2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

/**
 * A labeled name→number table for flat `{"name": number}` wire maps — the
 * friendly face for cost tables, weight maps, and any other "thing, amount"
 * object a scientist should never have to author as JSON.
 *
 *  - "table" (default): labeled columns (e.g. Reagent | Cost, $/g), one row per
 *    entry, add/remove rows, optional autocomplete suggestions sourced from
 *    in-app data (a native <datalist>, so typing stays unconstrained).
 *  - "raw" (escape hatch): a JSON <Textarea> for power users / paste-in. Parse
 *    errors surface inline; the last valid value is kept until the text parses.
 *
 * Contract mirrors the other Phase-7 field components: emits a plain object on
 * every change (empty/incomplete rows omitted; an all-empty table emits {}),
 * seeds from `initialValue` ONCE on mount, and is reset by bumping the React
 * `key` (create forms do this after a successful submit). The wire shape is
 * unchanged — only the authoring surface is new.
 */
export function KeyNumberTableField({
  label,
  onChange,
  initialValue = {},
  keyLabel = "Name",
  valueLabel = "Value",
  unit,
  keyPlaceholder,
  valuePlaceholder = "0.00",
  addLabel = "Add row",
  suggestions = [],
  suggestionsHint,
  description,
  idPrefix = "knt",
}: {
  label: string
  onChange: (next: Record<string, number>) => void
  initialValue?: Record<string, unknown>
  keyLabel?: string
  valueLabel?: string
  /** Display-only unit hint appended to the value column header, e.g. "$/g". */
  unit?: string
  keyPlaceholder?: string
  valuePlaceholder?: string
  addLabel?: string
  /** Optional autocomplete options for the name column (native datalist). */
  suggestions?: string[]
  /** Shown under the table when suggestions exist, e.g. "Suggestions come from this project's design space." */
  suggestionsHint?: string
  description?: string
  idPrefix?: string
}) {
  type Row = { id: number; key: string; value: string }

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

  const duplicateKeys = useMemo(() => {
    const seen = new Set<string>()
    const dups = new Set<string>()
    for (const r of rows) {
      const k = r.key.trim()
      if (!k) continue
      if (seen.has(k)) dups.add(k)
      seen.add(k)
    }
    return dups
  }, [rows])

  function assemble(nextRows: Row[]): Record<string, number> {
    const obj: Record<string, number> = {}
    for (const row of nextRows) {
      const key = row.key.trim()
      if (!key) continue
      const n = Number(row.value.trim())
      if (row.value.trim() === "" || !Number.isFinite(n)) continue
      // Later rows win on duplicate names — matches JSON.parse semantics so the
      // table and the raw escape hatch agree.
      obj[key] = n
    }
    return obj
  }

  function emit(nextRows: Row[]) {
    onChange(assemble(nextRows))
  }

  function updateRow(id: number, patch: Partial<Pick<Row, "key" | "value">>) {
    const next = rows.map((r) => (r.id === id ? { ...r, ...patch } : r))
    setRows(next)
    emit(next)
  }

  function addRow() {
    setRows((prev) => [...prev, { id: nextId, key: "", value: "" }])
    setNextId((n) => n + 1)
  }

  function removeRow(id: number) {
    const next = rows.filter((r) => r.id !== id)
    setRows(next)
    emit(next)
  }

  function enterRaw() {
    const obj = assemble(rows)
    setRawDraft(Object.keys(obj).length ? JSON.stringify(obj, null, 2) : "")
    setRawError("")
    setMode("raw")
  }

  function enterTable() {
    // Re-seed the rows from the raw draft's last valid value so raw-mode edits
    // carry back into the table.
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
        // Unparseable text never reached onChange; keep the existing rows.
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
      setRawError('Must be a JSON object of numbers (e.g. {"Pd(OAc)2": 12.5}).')
      return
    }
    const obj: Record<string, number> = {}
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      // Only real numbers, or numeric strings, count. `Number(null)`, `Number("")`,
      // `Number(false)`, `Number([5])` are all finite in JS — reject on the INPUT type,
      // not the coerced result, so the table and the raw hatch agree on what a number is.
      let n: number
      if (typeof v === "number") {
        n = v
      } else if (typeof v === "string" && v.trim() !== "") {
        n = Number(v)
      } else {
        setRawError(`"${k}" must be a number.`)
        return
      }
      if (!Number.isFinite(n)) {
        setRawError(`"${k}" must be a number.`)
        return
      }
      obj[k] = n
    }
    setRawError("")
    onChange(obj)
  }

  const valueHeader = unit ? `${valueLabel} (${unit})` : valueLabel

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
                <span className="flex-[2]">{valueHeader}</span>
              </div>
              {rows.map((row) => {
                const isDup = row.key.trim() !== "" && duplicateKeys.has(row.key.trim())
                return (
                  <div key={row.id} className="flex items-center gap-2">
                    <div className="flex-[3]">
                      <Input
                        aria-label={`${keyLabel} (row)`}
                        aria-invalid={isDup || undefined}
                        list={suggestions.length ? listId : undefined}
                        value={row.key}
                        placeholder={keyPlaceholder ?? keyLabel}
                        onChange={(e) => updateRow(row.id, { key: e.target.value })}
                      />
                    </div>
                    <div className="flex-[2]">
                      <Input
                        aria-label={`${valueHeader} (row)`}
                        value={row.value}
                        placeholder={valuePlaceholder}
                        inputMode="decimal"
                        onChange={(e) => updateRow(row.id, { value: e.target.value })}
                      />
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
                )
              })}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              No entries yet. {addLabel ? `Use “${addLabel}” to start.` : ""}
            </p>
          )}

          {duplicateKeys.size > 0 ? (
            <p className="text-[11px] text-destructive">
              Duplicate {keyLabel.toLowerCase()}: {[...duplicateKeys].join(", ")} — the last row
              wins.
            </p>
          ) : null}

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
            className="min-h-[120px] font-mono text-xs"
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

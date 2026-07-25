"use client"

import { useId, useState } from "react"
import { Braces, Plus, Rows2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

/**
 * A labeled two-column pair editor for `[["a", "b"], ...]` wire arrays —
 * e.g. incompatible reagent pairs — with optional autocomplete suggestions
 * shared by both columns and a raw-JSON escape hatch.
 *
 * Emits an array of 2-string arrays (rows with either side blank omitted;
 * an all-empty editor emits []). Seeds ONCE on mount; resets via `key` bump.
 * Legacy rows that are not 2-lists (e.g. `{"left": ..., "right": ...}` or a
 * plain string) are surfaced through the JSON escape hatch rather than lost:
 * they seed the table only when a left/right reading exists.
 */
export function PairListField({
  label,
  onChange,
  initialValue = [],
  leftLabel = "Component A",
  rightLabel = "Component B",
  addLabel = "Add pair",
  suggestions = [],
  suggestionsHint,
  description,
  idPrefix = "plf",
}: {
  label: string
  onChange: (next: [string, string][]) => void
  initialValue?: unknown[]
  leftLabel?: string
  rightLabel?: string
  addLabel?: string
  suggestions?: string[]
  suggestionsHint?: string
  description?: string
  idPrefix?: string
}) {
  type Row = { id: number; left: string; right: string }

  const reactId = useId()
  const listId = `${idPrefix}-${reactId}-suggestions`

  const [rows, setRows] = useState<Row[]>(() => {
    let id = 0
    const seeded: Row[] = []
    for (const item of initialValue) {
      if (Array.isArray(item) && item.length >= 2) {
        seeded.push({ id: id++, left: String(item[0] ?? ""), right: String(item[1] ?? "") })
      } else if (item && typeof item === "object") {
        const rec = item as Record<string, unknown>
        const left = rec.left ?? rec.a
        const right = rec.right ?? rec.b
        if (left != null || right != null) {
          seeded.push({ id: id++, left: String(left ?? ""), right: String(right ?? "") })
        }
      }
    }
    return seeded
  })
  const [nextId, setNextId] = useState(() => 10_000)
  const [mode, setMode] = useState<"table" | "raw">("table")
  const [rawDraft, setRawDraft] = useState("")
  const [rawError, setRawError] = useState("")

  function assemble(nextRows: Row[]): [string, string][] {
    return nextRows
      .map((r) => [r.left.trim(), r.right.trim()] as [string, string])
      .filter(([a, b]) => a !== "" && b !== "")
  }

  function updateRow(id: number, patch: Partial<Pick<Row, "left" | "right">>) {
    const next = rows.map((r) => (r.id === id ? { ...r, ...patch } : r))
    setRows(next)
    onChange(assemble(next))
  }

  function addRow() {
    setRows((prev) => [...prev, { id: nextId, left: "", right: "" }])
    setNextId((n) => n + 1)
  }

  function removeRow(id: number) {
    const next = rows.filter((r) => r.id !== id)
    setRows(next)
    onChange(assemble(next))
  }

  function enterRaw() {
    const list = assemble(rows)
    setRawDraft(list.length ? JSON.stringify(list, null, 2) : "")
    setRawError("")
    setMode("raw")
  }

  function enterTable() {
    const trimmed = rawDraft.trim()
    if (!trimmed) {
      // The raw box was cleared (onRawChange already emitted []). Clear the rows to match.
      setRows([])
      onChange([])
    } else if (!rawError) {
      try {
        const parsed = JSON.parse(trimmed) as unknown[]
        let id = nextId
        const seeded: Row[] = []
        for (const item of parsed) {
          if (Array.isArray(item) && item.length >= 2) {
            seeded.push({ id: id++, left: String(item[0] ?? ""), right: String(item[1] ?? "") })
          }
        }
        setRows(seeded)
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
      onChange([])
      return
    }
    let parsed: unknown
    try {
      parsed = JSON.parse(trimmed)
    } catch {
      setRawError("Enter valid JSON, or switch back to the table.")
      return
    }
    if (!Array.isArray(parsed) || parsed.some((p) => !Array.isArray(p) || p.length < 2)) {
      setRawError('Must be a JSON array of pairs (e.g. [["oxidizer", "amine"]]).')
      return
    }
    setRawError("")
    // Trim both sides and drop any pair with a blank side, exactly like the table's
    // `assemble` — the raw hatch can never emit a half-blank pair the table would omit.
    const pairs: [string, string][] = []
    for (const p of parsed as unknown[][]) {
      const a = p[0] == null ? "" : String(p[0]).trim()
      const b = p[1] == null ? "" : String(p[1]).trim()
      if (a !== "" && b !== "") pairs.push([a, b])
    }
    onChange(pairs)
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
              <Rows2 className="h-3.5 w-3.5" />
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
                <span className="flex-1">{leftLabel}</span>
                <span className="flex-1">{rightLabel}</span>
              </div>
              {rows.map((row) => (
                <div key={row.id} className="flex items-center gap-2">
                  <Input
                    aria-label={`${leftLabel} (row)`}
                    className="flex-1"
                    list={suggestions.length ? listId : undefined}
                    value={row.left}
                    placeholder={leftLabel}
                    onChange={(e) => updateRow(row.id, { left: e.target.value })}
                  />
                  <Input
                    aria-label={`${rightLabel} (row)`}
                    className="flex-1"
                    list={suggestions.length ? listId : undefined}
                    value={row.right}
                    placeholder={rightLabel}
                    onChange={(e) => updateRow(row.id, { right: e.target.value })}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label="Remove pair"
                    onClick={() => removeRow(row.id)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              No pairs yet. {addLabel ? `Use “${addLabel}” to start.` : ""}
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

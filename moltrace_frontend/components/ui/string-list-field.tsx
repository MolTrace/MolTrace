"use client"

import { useId, useState } from "react"
import { Braces, ListPlus, Plus, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

/**
 * A labeled list-of-strings editor for `["value", ...]` wire arrays — blocked
 * reagents, required controls, tag lists — with one input per row, optional
 * autocomplete suggestions (native <datalist>), and a raw-JSON escape hatch.
 *
 * Contract mirrors the other Phase-7 field components: emits a plain string
 * array on every change (blank rows omitted; an all-empty list emits []),
 * seeds from `initialValue` ONCE on mount, resets via a React `key` bump.
 */
export function StringListField({
  label,
  onChange,
  initialValue = [],
  itemLabel = "Item",
  itemPlaceholder,
  addLabel = "Add item",
  suggestions = [],
  suggestionsHint,
  description,
  idPrefix = "slf",
}: {
  label: string
  onChange: (next: string[]) => void
  initialValue?: unknown[]
  itemLabel?: string
  itemPlaceholder?: string
  addLabel?: string
  suggestions?: string[]
  suggestionsHint?: string
  description?: string
  idPrefix?: string
}) {
  type Row = { id: number; value: string }

  const reactId = useId()
  const listId = `${idPrefix}-${reactId}-suggestions`

  const [rows, setRows] = useState<Row[]>(() =>
    initialValue.filter((v) => v != null).map((v, i) => ({ id: i, value: String(v) })),
  )
  const [nextId, setNextId] = useState(() => 10_000)
  const [mode, setMode] = useState<"list" | "raw">("list")
  const [rawDraft, setRawDraft] = useState("")
  const [rawError, setRawError] = useState("")

  function assemble(nextRows: Row[]): string[] {
    return nextRows.map((r) => r.value.trim()).filter((v) => v !== "")
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
    setRawDraft(list.length ? JSON.stringify(list, null, 2) : "")
    setRawError("")
    setMode("raw")
  }

  function enterList() {
    const trimmed = rawDraft.trim()
    if (trimmed && !rawError) {
      try {
        const parsed = JSON.parse(trimmed) as unknown[]
        let id = nextId
        setRows(parsed.filter((v) => v != null).map((v) => ({ id: id++, value: String(v) })))
        setNextId(id)
      } catch {
        // Unparseable text never reached onChange; keep the existing rows.
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
      setRawError('Must be a JSON array (e.g. ["DMF", "benzene"]).')
      return
    }
    setRawError("")
    // Trim and drop blanks, exactly like the list view's `assemble` — so the raw
    // hatch can never emit an empty-string entry the list can't represent.
    onChange(
      parsed
        .map((v) => (v == null ? "" : String(v).trim()))
        .filter((v) => v !== ""),
    )
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
                    list={suggestions.length ? listId : undefined}
                    value={row.value}
                    placeholder={itemPlaceholder ?? itemLabel}
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

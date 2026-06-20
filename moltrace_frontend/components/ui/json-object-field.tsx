"use client"

import { useState } from "react"
import { Braces, ListTree } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  StructuredJsonObjectEditor,
  type JsonValueType,
  type StructuredJsonField,
} from "@/components/ui/structured-json-editor"

/**
 * A labeled JSON-object input with two modes:
 *
 *  - "structured" (default): the friendly {@link StructuredJsonObjectEditor} —
 *    labeled fields and/or add-your-own key/value rows. No braces to author.
 *  - "raw" (advanced): a JSON <Textarea> escape hatch for nested / complex
 *    objects the flat editor can't express. Parse errors surface inline and the
 *    last valid value is kept until the text is valid again.
 *
 * Use this (rather than the bare structured editor) for free-form scientific
 * objects that *may* be nested — the structured mode covers the common flat
 * case while raw mode preserves full fidelity. The emitted value is always a
 * plain JSON object; the wire contract is unchanged.
 *
 * Seeds from `initialValue` on mount; reset by bumping the React `key`.
 */
export function JsonObjectField({
  label,
  onChange,
  initialValue = {},
  fields = [],
  allowCustomKeys = true,
  customValueType = "auto",
  description,
  addLabel = "Add field",
  keyPlaceholder = "key",
  valuePlaceholder = "value",
  idPrefix = "json-field",
}: {
  label: string
  onChange: (next: Record<string, unknown>) => void
  initialValue?: Record<string, unknown>
  fields?: StructuredJsonField[]
  allowCustomKeys?: boolean
  customValueType?: JsonValueType
  description?: string
  addLabel?: string
  keyPlaceholder?: string
  valuePlaceholder?: string
  idPrefix?: string
}) {
  const [obj, setObj] = useState<Record<string, unknown>>(initialValue)
  const [mode, setMode] = useState<"structured" | "raw">("structured")
  // Bumped when we re-enter structured mode so the (mount-seeded) editor
  // remounts and reflects edits made in raw mode.
  const [seedVersion, setSeedVersion] = useState(0)
  const [rawDraft, setRawDraft] = useState("")
  const [rawError, setRawError] = useState("")

  function commit(next: Record<string, unknown>) {
    setObj(next)
    onChange(next)
  }

  function enterRaw() {
    const keys = Object.keys(obj)
    setRawDraft(keys.length ? JSON.stringify(obj, null, 2) : "")
    setRawError("")
    setMode("raw")
  }

  function enterStructured() {
    setSeedVersion((v) => v + 1)
    setRawError("")
    setMode("structured")
  }

  function onRawChange(text: string) {
    setRawDraft(text)
    const trimmed = text.trim()
    if (!trimmed) {
      setRawError("")
      commit({})
      return
    }
    let parsed: unknown
    try {
      parsed = JSON.parse(trimmed)
    } catch {
      setRawError("Enter valid JSON, or switch to structured fields.")
      return
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      setRawError("Must be a JSON object (e.g. {\"key\": \"value\"}).")
      return
    }
    setRawError("")
    commit(parsed as Record<string, unknown>)
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
          onClick={mode === "structured" ? enterRaw : enterStructured}
        >
          {mode === "structured" ? (
            <>
              <Braces className="h-3.5 w-3.5" />
              Edit as raw JSON
            </>
          ) : (
            <>
              <ListTree className="h-3.5 w-3.5" />
              Use structured fields
            </>
          )}
        </Button>
      </div>

      {mode === "structured" ? (
        <StructuredJsonObjectEditor
          key={`${idPrefix}-${seedVersion}`}
          idPrefix={idPrefix}
          initialValue={obj}
          fields={fields}
          onChange={commit}
          allowCustomKeys={allowCustomKeys}
          customValueType={customValueType}
          addLabel={addLabel}
          keyPlaceholder={keyPlaceholder}
          valuePlaceholder={valuePlaceholder}
          description={description}
        />
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

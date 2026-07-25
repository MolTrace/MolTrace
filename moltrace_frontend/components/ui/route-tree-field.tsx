"use client"

import { useState } from "react"
import { Braces, ListTree, Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

/**
 * A recursive builder for a retrosynthetic route tree
 * (`{smiles, reagents[], solvent?, children[]}`) — the R13 route-scoring input.
 * Each node is a product SMILES with optional reagents/solvent and a list of
 * precursor child nodes; the structure nests arbitrarily. A raw-JSON escape
 * hatch covers paste-in from an external planner.
 *
 * Emits the nested object on every change. `smiles` is always present (possibly
 * ""); `reagents` and `children` are always arrays; `solvent` is included only
 * when set. Seeds ONCE on mount; reset via a React `key` bump.
 */

export type RouteTreeValue = {
  smiles: string
  // The reagents field is kept as the raw comma-separated TEXT the user types (not a
  // pre-split array), so the input can hold a trailing comma while typing a second reagent.
  // It is split into the array only at serialize time.
  reagentsText: string
  solvent?: string
  children: RouteTreeValue[]
}

function coerceNode(raw: unknown): RouteTreeValue {
  const rec = raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {}
  const reagentsText = Array.isArray(rec.reagents)
    ? rec.reagents.filter((v) => v != null).map((v) => String(v)).join(", ")
    : ""
  const children = Array.isArray(rec.children) ? rec.children.map(coerceNode) : []
  const node: RouteTreeValue = {
    smiles: typeof rec.smiles === "string" ? rec.smiles : "",
    reagentsText,
    children,
  }
  if (typeof rec.solvent === "string" && rec.solvent.trim() !== "") node.solvent = rec.solvent
  return node
}

/** Drop empties so the emitted object stays clean (reagents/solvent/children omitted when unused). */
function serializeNode(node: RouteTreeValue): Record<string, unknown> {
  const out: Record<string, unknown> = { smiles: node.smiles.trim() }
  const reagents = node.reagentsText
    .split(",")
    .map((r) => r.trim())
    .filter((r) => r !== "")
  if (reagents.length) out.reagents = reagents
  if (node.solvent && node.solvent.trim() !== "") out.solvent = node.solvent.trim()
  const children = node.children.map(serializeNode).filter((c) => c.smiles !== "")
  if (children.length) out.children = children
  return out
}

function emptyNode(): RouteTreeValue {
  return { smiles: "", reagentsText: "", children: [] }
}

function RouteNodeEditor({
  node,
  onChange,
  onRemove,
  depth,
  label,
}: {
  node: RouteTreeValue
  onChange: (next: RouteTreeValue) => void
  onRemove?: () => void
  depth: number
  label: string
}) {
  return (
    <div
      className="space-y-2 rounded-lg border bg-muted/20 p-3"
      style={{ marginLeft: depth > 0 ? 12 : 0 }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </span>
        {onRemove ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={`Remove ${label}`}
            onClick={onRemove}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        ) : null}
      </div>

      <div className="space-y-1">
        <Label className="text-xs">{depth === 0 ? "Product SMILES" : "Precursor SMILES"}</Label>
        <Input
          aria-label={`${label} SMILES`}
          value={node.smiles}
          placeholder="CCOC(C)=O"
          onChange={(e) => onChange({ ...node, smiles: e.target.value })}
        />
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <div className="space-y-1">
          <Label className="text-xs">Reagents (comma-separated)</Label>
          <Input
            aria-label={`${label} reagents`}
            value={node.reagentsText}
            placeholder="OS(O)(=O)=O, ClCCl"
            onChange={(e) => onChange({ ...node, reagentsText: e.target.value })}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Solvent (optional)</Label>
          <Input
            aria-label={`${label} solvent`}
            value={node.solvent ?? ""}
            placeholder="ethanol"
            onChange={(e) => onChange({ ...node, solvent: e.target.value })}
          />
        </div>
      </div>

      {node.children.length > 0 ? (
        <div className="space-y-2">
          {node.children.map((child, i) => (
            <RouteNodeEditor
              key={i}
              node={child}
              depth={depth + 1}
              label={`Precursor ${i + 1}`}
              onChange={(next) => {
                const children = node.children.slice()
                children[i] = next
                onChange({ ...node, children })
              }}
              onRemove={() => {
                const children = node.children.slice()
                children.splice(i, 1)
                onChange({ ...node, children })
              }}
            />
          ))}
        </div>
      ) : null}

      <Button
        type="button"
        variant="outline"
        size="sm"
        className="gap-1.5"
        onClick={() => onChange({ ...node, children: [...node.children, emptyNode()] })}
      >
        <Plus className="h-3.5 w-3.5" />
        Add precursor
      </Button>
    </div>
  )
}

export function RouteTreeField({
  label,
  onChange,
  initialValue,
  description,
}: {
  label: string
  onChange: (next: Record<string, unknown>) => void
  initialValue?: Record<string, unknown>
  description?: string
}) {
  const [tree, setTree] = useState<RouteTreeValue>(() =>
    initialValue ? coerceNode(initialValue) : emptyNode(),
  )
  const [mode, setMode] = useState<"tree" | "raw">("tree")
  const [rawDraft, setRawDraft] = useState("")
  const [rawError, setRawError] = useState("")

  function commit(next: RouteTreeValue) {
    setTree(next)
    onChange(serializeNode(next))
  }

  function enterRaw() {
    setRawDraft(JSON.stringify(serializeNode(tree), null, 2))
    setRawError("")
    setMode("raw")
  }

  function enterTree() {
    const trimmed = rawDraft.trim()
    if (!trimmed) {
      // The raw box was cleared (onRawChange already emitted {}). Reset the builder to match,
      // so the displayed tree and the emitted value can't disagree.
      const empty = emptyNode()
      setTree(empty)
      onChange(serializeNode(empty))
    } else if (!rawError) {
      try {
        const next = coerceNode(JSON.parse(trimmed))
        setTree(next)
        onChange(serializeNode(next))
      } catch {
        /* keep existing tree */
      }
    }
    setRawError("")
    setMode("tree")
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
      setRawError("Enter valid JSON, or switch back to the builder.")
      return
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      setRawError('Must be a JSON object (e.g. {"smiles": "...", "children": []}).')
      return
    }
    setRawError("")
    onChange(serializeNode(coerceNode(parsed)))
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
          onClick={mode === "tree" ? enterRaw : enterTree}
        >
          {mode === "tree" ? (
            <>
              <Braces className="h-3.5 w-3.5" />
              Edit as JSON
            </>
          ) : (
            <>
              <ListTree className="h-3.5 w-3.5" />
              Use builder
            </>
          )}
        </Button>
      </div>

      {mode === "tree" ? (
        <div className="space-y-2">
          {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
          <RouteNodeEditor node={tree} onChange={commit} depth={0} label="Target" />
        </div>
      ) : (
        <div className="space-y-1">
          <Textarea
            aria-label={`${label} (raw JSON)`}
            className="min-h-[160px] font-mono text-xs"
            value={rawDraft}
            spellCheck={false}
            placeholder='{"smiles": "", "children": []}'
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

export type CompactLargePayloadOptions = {
  maxArrayLength?: number
  arrayPreviewLength?: number
  maxStringLength?: number
  maxDepth?: number
}

const DEFAULT_MAX_ARRAY_LENGTH = 80
const DEFAULT_ARRAY_PREVIEW_LENGTH = 8
const DEFAULT_MAX_STRING_LENGTH = 4_000
const DEFAULT_MAX_DEPTH = 7

type CompactOptionsResolved = {
  maxArrayLength: number
  arrayPreviewLength: number
  maxStringLength: number
  maxDepth: number
}

function resolveOptions(options: CompactLargePayloadOptions): CompactOptionsResolved {
  return {
    maxArrayLength: options.maxArrayLength ?? DEFAULT_MAX_ARRAY_LENGTH,
    arrayPreviewLength: options.arrayPreviewLength ?? DEFAULT_ARRAY_PREVIEW_LENGTH,
    maxStringLength: options.maxStringLength ?? DEFAULT_MAX_STRING_LENGTH,
    maxDepth: options.maxDepth ?? DEFAULT_MAX_DEPTH,
  }
}

function compactArrayLike(
  value: ArrayLike<unknown>,
  options: CompactOptionsResolved,
  depth: number,
  seen: WeakSet<object>,
) {
  const previewLength = Math.max(1, options.arrayPreviewLength)
  const headCount = Math.min(previewLength, value.length)
  const tailCount = Math.min(previewLength, Math.max(0, value.length - headCount))
  const head = Array.from({ length: headCount }, (_, i) =>
    compactLargePayloadForDisplay(value[i], options, depth + 1, seen),
  )
  const tailStart = Math.max(headCount, value.length - tailCount)
  const tail = Array.from({ length: Math.max(0, value.length - tailStart) }, (_, i) =>
    compactLargePayloadForDisplay(value[tailStart + i], options, depth + 1, seen),
  )
  return {
    __compact__: "large-array",
    length: value.length,
    omitted: Math.max(0, value.length - head.length - tail.length),
    head,
    tail,
  }
}

export function compactLargePayloadForDisplay(
  value: unknown,
  optionsInput: CompactLargePayloadOptions | CompactOptionsResolved = {},
  depth = 0,
  seen: WeakSet<object> = new WeakSet<object>(),
): unknown {
  const options =
    "maxArrayLength" in optionsInput &&
    "arrayPreviewLength" in optionsInput &&
    "maxStringLength" in optionsInput &&
    "maxDepth" in optionsInput
      ? (optionsInput as CompactOptionsResolved)
      : resolveOptions(optionsInput)

  if (typeof value === "string") {
    if (value.length <= options.maxStringLength) return value
    return `${value.slice(0, options.maxStringLength)}\n...[truncated ${value.length - options.maxStringLength} chars]`
  }
  if (value == null || typeof value !== "object") return value
  if (seen.has(value)) return "[Circular]"
  if (depth >= options.maxDepth) return "[Max depth reached]"

  seen.add(value)
  if (Array.isArray(value)) {
    if (value.length > options.maxArrayLength) {
      return compactArrayLike(value, options, depth, seen)
    }
    return value.map((item) => compactLargePayloadForDisplay(item, options, depth + 1, seen))
  }

  if (ArrayBuffer.isView(value) && !(value instanceof DataView)) {
    const view = value as unknown as ArrayLike<unknown>
    if (view.length > options.maxArrayLength) {
      return compactArrayLike(view, options, depth, seen)
    }
    return Array.from({ length: view.length }, (_, i) =>
      compactLargePayloadForDisplay(view[i], options, depth + 1, seen),
    )
  }

  const out: Record<string, unknown> = {}
  for (const [key, child] of Object.entries(value)) {
    out[key] = compactLargePayloadForDisplay(child, options, depth + 1, seen)
  }
  return out
}

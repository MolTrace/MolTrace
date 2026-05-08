import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatStableUtcDateTime(
  value: string | number | Date | null | undefined,
  fallback = '—',
  options: { includeSeconds?: boolean } = {},
): string {
  if (value == null) return fallback

  let ms: number
  if (value instanceof Date) {
    ms = value.getTime()
  } else if (typeof value === 'number') {
    ms = value
  } else {
    const trimmed = value.trim()
    if (!trimmed) return fallback
    ms = Date.parse(trimmed)
    if (!Number.isFinite(ms)) return trimmed
  }

  if (!Number.isFinite(ms)) return fallback

  const d = new Date(ms)
  const pad = (n: number) => String(n).padStart(2, '0')
  const seconds = options.includeSeconds ? `:${pad(d.getUTCSeconds())}` : ''
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(
    d.getUTCHours(),
  )}:${pad(d.getUTCMinutes())}${seconds} UTC`
}

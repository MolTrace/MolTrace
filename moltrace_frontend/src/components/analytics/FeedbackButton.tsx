"use client"

import { useState } from "react"
import { usePathname } from "next/navigation"
import { MessageSquare } from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"

export const ANALYTICS_FEEDBACK_TYPES = [
  "useful",
  "not_useful",
  "confusing",
  "bug",
  "feature_request",
  "other",
] as const

export type AnalyticsFeedbackType = (typeof ANALYTICS_FEEDBACK_TYPES)[number]

const FEEDBACK_TYPE_LABELS: Record<AnalyticsFeedbackType, string> = {
  useful: "Useful",
  not_useful: "Not useful",
  confusing: "Confusing",
  bug: "Bug",
  feature_request: "Feature request",
  other: "Other",
}

const MAX_COMMENT = 5_000

export type FeedbackButtonProps = {
  /** Stored in metadata_json.module — page or feature context only. */
  module: string
  projectId?: number | null
  sessionId?: number | null
  className?: string
  buttonClassName?: string
  align?: "start" | "center" | "end"
}

/** Coerce project selector value to API `project_id` (integer) or null. */
export function toFeedbackProjectId(value: string | null | undefined): number | null {
  if (value == null || !String(value).trim()) return null
  const n = Number(String(value).trim())
  if (!Number.isFinite(n) || n < 1) return null
  return Math.trunc(n)
}

/** Coerce backend session id string to API `session_id` when it is a positive integer. */
export function toFeedbackSessionId(value: string | null | undefined): number | null {
  if (value == null || !String(value).trim()) return null
  const t = String(value).trim()
  if (!/^\d{1,12}$/.test(t)) return null
  const n = parseInt(t, 10)
  return Number.isFinite(n) && n > 0 ? n : null
}

export function FeedbackButton({
  module,
  projectId = null,
  sessionId = null,
  className,
  buttonClassName,
  align = "end",
}: FeedbackButtonProps) {
  const pathname = usePathname()
  const route = pathname?.trim() || "/"

  const [open, setOpen] = useState(false)
  const [feedbackType, setFeedbackType] = useState<AnalyticsFeedbackType>("useful")
  const [ratingChoice, setRatingChoice] = useState<string>("none")
  const [comment, setComment] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [done, setDone] = useState(false)

  function resetForm() {
    setFeedbackType("useful")
    setRatingChoice("none")
    setComment("")
    setError("")
    setDone(false)
  }

  async function handleSubmit() {
    setError("")
    setBusy(true)
    const rating = ratingChoice === "none" ? null : Number.parseInt(ratingChoice, 10)
    const safeRating =
      rating != null && Number.isFinite(rating) && rating >= 1 && rating <= 5 ? rating : null
    const trimmed = comment.trim().slice(0, MAX_COMMENT)
    const payload = {
      project_id: projectId ?? null,
      session_id: sessionId ?? null,
      feedback_type: feedbackType,
      rating: safeRating,
      comment: trimmed || null,
      metadata_json: {
        route,
        module,
      },
    }
    try {
      await apiFetch("/analytics/feedback", {
        method: "POST",
        body: payload,
      })
      setDone(true)
      setTimeout(() => {
        setOpen(false)
        resetForm()
      }, 1600)
    } catch (e) {
      setError(formatApiError(e, "Could not send feedback."))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={cn("inline-flex", className)}>
      <Popover
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (!next) resetForm()
        }}
      >
        <PopoverTrigger asChild>
          <Button type="button" variant="outline" size="sm" className={buttonClassName}>
            <MessageSquare className="mr-2 h-4 w-4" />
            Feedback
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-80 space-y-3 p-4" align={align}>
          <div className="space-y-1">
            <p className="text-sm font-medium">Product feedback</p>
            <p className="text-xs text-muted-foreground">
              Route and module only — do not paste spectra, peaks, or structures.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="analytics-feedback-type">Type</Label>
            <Select value={feedbackType} onValueChange={(v) => setFeedbackType(v as AnalyticsFeedbackType)}>
              <SelectTrigger id="analytics-feedback-type" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ANALYTICS_FEEDBACK_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {FEEDBACK_TYPE_LABELS[t]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="analytics-feedback-rating">Rating (optional)</Label>
            <Select value={ratingChoice} onValueChange={setRatingChoice}>
              <SelectTrigger id="analytics-feedback-rating" className="w-full">
                <SelectValue placeholder="No rating" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No rating</SelectItem>
                {[1, 2, 3, 4, 5].map((n) => (
                  <SelectItem key={n} value={String(n)}>
                    {n}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="analytics-feedback-comment">Comment (optional)</Label>
            <Textarea
              id="analytics-feedback-comment"
              rows={3}
              value={comment}
              onChange={(e) => setComment(e.target.value.slice(0, MAX_COMMENT))}
              placeholder="Brief note about workflow or value (no scientific payloads)."
              className="resize-y text-sm"
            />
          </div>

          {error ? <p className="text-xs text-destructive">{error}</p> : null}
          {done ? (
            <p className="text-xs text-muted-foreground">Thanks — feedback recorded.</p>
          ) : null}

          <Button type="button" size="sm" className="w-full" disabled={busy} onClick={() => void handleSubmit()}>
            {busy ? "Sending…" : "Submit"}
          </Button>
        </PopoverContent>
      </Popover>
    </div>
  )
}

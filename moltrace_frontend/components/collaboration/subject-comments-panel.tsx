"use client"

// Notes left on a filing or a campaign, and the one action they support after the fact:
// marking a note settled. Resolving keeps what was said — nothing here deletes a comment.
//
// Rendered as a tab of `subject-collaboration-panel.tsx`.
//
// Spectroscopy sessions are NOT served here; their notes can be anchored to a specific
// piece of evidence, which a filing has no equivalent of. `SubjectType` excludes them.
//
// The not-found state is load-bearing: a filing that belongs to another organization
// answers the same way one that never existed does, so this says "no longer available",
// never "you do not have permission". See lib/collaboration/subject-collaboration.ts.

import { useCallback, useEffect, useState } from "react"
import { Loader2 } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { statusLabel } from "@/lib/ui/status"
import { formatStableUtcDateTime } from "@/lib/utils"
import {
  subjectKindLabel,
  type SubjectCollaborationError,
  type SubjectSurfaceBodyProps,
} from "@/lib/collaboration/subject-collaboration"
import {
  COMMENT_TYPES,
  describeSubjectCommentError,
  leaveSubjectComment,
  listSubjectComments,
  sortSubjectComments,
  unresolvedCommentCount,
  updateSubjectComment,
  type CommentType,
  type SubjectCommentRecord,
} from "@/lib/collaboration/subject-comments"

export function SubjectCommentsBody({
  subjectType,
  subjectId,
  onAttentionCountChange,
}: SubjectSurfaceBodyProps) {
  const kind = subjectKindLabel(subjectType)

  const [comments, setComments] = useState<SubjectCommentRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<SubjectCollaborationError | null>(null)

  const [draft, setDraft] = useState("")
  const [commentType, setCommentType] = useState<CommentType>("note")
  const [posting, setPosting] = useState(false)
  const [postError, setPostError] = useState("")

  const [savingCommentId, setSavingCommentId] = useState<number | null>(null)
  const [saveError, setSaveError] = useState("")

  const refresh = useCallback(async () => {
    if (subjectId == null) return
    setLoading(true)
    setLoadError(null)
    try {
      setComments(sortSubjectComments(await listSubjectComments(subjectType, subjectId)))
    } catch (err) {
      setComments([])
      setLoadError(describeSubjectCommentError(err, subjectType))
    } finally {
      setLoading(false)
    }
  }, [subjectType, subjectId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const unresolved = unresolvedCommentCount(comments)

  useEffect(() => {
    onAttentionCountChange?.(unresolved)
  }, [unresolved, onAttentionCountChange])

  async function post() {
    if (subjectId == null) return
    const trimmed = draft.trim()
    if (!trimmed) {
      setPostError("Write something before posting.")
      return
    }
    setPosting(true)
    setPostError("")
    try {
      await leaveSubjectComment({ subjectType, subjectId, comment: trimmed, commentType })
      setDraft("")
      setCommentType("note")
      await refresh()
    } catch (err) {
      setPostError(describeSubjectCommentError(err, subjectType).message)
    } finally {
      setPosting(false)
    }
  }

  async function setResolved(commentId: number, resolved: boolean) {
    setSavingCommentId(commentId)
    setSaveError("")
    try {
      await updateSubjectComment(commentId, { resolved })
      await refresh()
    } catch (err) {
      setSaveError(describeSubjectCommentError(err, subjectType).message)
    } finally {
      setSavingCommentId(null)
    }
  }

  return (
    <div className="space-y-5">
      <p className="text-sm leading-relaxed text-muted-foreground">
        Leave a note on this {kind}. Everyone who can open it reads the same thread. Resolving a
        note marks it settled — it stays on the record either way.
      </p>

      {subjectId == null ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : loadError ? (
        <Alert variant={loadError.kind === "not_found" ? "default" : "destructive"}>
          <AlertTitle>
            {loadError.kind === "not_found"
              ? `This ${kind} is not available`
              : "Comments could not be loaded"}
          </AlertTitle>
          <AlertDescription className="text-sm leading-relaxed">{loadError.message}</AlertDescription>
        </Alert>
      ) : (
        <>
          <div className="grid gap-4">
            <div className="space-y-2">
              <Label htmlFor="ssc-comment" className="text-sm">
                Your note <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="ssc-comment"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={3}
                placeholder="What do you want the next reader to know?"
              />
            </div>
            <div className="space-y-2 sm:max-w-xs">
              <Label htmlFor="ssc-type" className="text-sm">
                Kind of note
              </Label>
              {/* ``value`` stays the stored token; only the label is humanized. */}
              <Select value={commentType} onValueChange={(v) => setCommentType(v as CommentType)}>
                <SelectTrigger id="ssc-type" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {COMMENT_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {statusLabel(t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {postError ? (
            <Alert variant="destructive">
              <AlertDescription className="text-sm">{postError}</AlertDescription>
            </Alert>
          ) : null}

          <Button type="button" variant="outline" size="sm" disabled={posting} onClick={() => void post()}>
            {posting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Post note
          </Button>

          {saveError ? (
            <Alert variant="destructive">
              <AlertDescription className="text-sm">{saveError}</AlertDescription>
            </Alert>
          ) : null}

          {loading ? (
            <p className="text-sm text-muted-foreground">Loading notes…</p>
          ) : comments.length === 0 ? (
            <p className="text-sm text-muted-foreground">No one has left a note on this {kind} yet.</p>
          ) : (
            <ul className="space-y-3">
              {comments.map((comment) => {
                const commentId = Number(comment.id)
                const resolved = Boolean(comment.resolved)
                return (
                  <li
                    key={commentId}
                    className={`rounded-lg border border-border/60 p-3 ${resolved ? "opacity-60" : ""}`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{statusLabel(comment.comment_type)}</Badge>
                      {resolved ? <Badge variant="secondary">Resolved</Badge> : null}
                      <span className="text-xs text-muted-foreground">
                        {comment.author_email || "Author not recorded"}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {formatStableUtcDateTime(comment.created_at)}
                      </span>
                    </div>
                    <p className="mt-2 whitespace-pre-wrap text-sm">{comment.comment}</p>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="mt-2"
                      disabled={savingCommentId === commentId}
                      onClick={() => void setResolved(commentId, !resolved)}
                    >
                      {resolved ? "Reopen" : "Mark resolved"}
                    </Button>
                  </li>
                )
              })}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

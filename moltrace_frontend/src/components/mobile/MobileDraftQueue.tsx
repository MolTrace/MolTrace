"use client"

import { useEffect, useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  addOfflineDraft,
  clearRejectedOfflineDrafts,
  getOfflineDrafts,
  getServerActionDrafts,
  type MobileDraftDecisionStatus,
  type MobileOfflineDraft,
  syncOfflineDraftsNow,
} from "@/src/lib/mobile/offline-drafts"

const STATUS_OPTIONS: MobileDraftDecisionStatus[] = ["draft", "open", "in_progress", "resolved", "deferred", "approve", "reject"]

export function MobileDraftQueue() {
  const [online, setOnline] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [syncInfo, setSyncInfo] = useState("")
  const [drafts, setDrafts] = useState<MobileOfflineDraft[]>([])
  const [actionType, setActionType] = useState("add_comment")
  const [targetType, setTargetType] = useState("report")
  const [targetId, setTargetId] = useState("")
  const [shortComment, setShortComment] = useState("")
  const [decisionStatus, setDecisionStatus] = useState<MobileDraftDecisionStatus>("draft")

  useEffect(() => {
    setDrafts(getOfflineDrafts())
    const handleOnlineState = () => setOnline(navigator.onLine)
    handleOnlineState()
    window.addEventListener("online", handleOnlineState)
    window.addEventListener("offline", handleOnlineState)
    return () => {
      window.removeEventListener("online", handleOnlineState)
      window.removeEventListener("offline", handleOnlineState)
    }
  }, [])

  async function handleSyncNow() {
    setLoading(true)
    setError("")
    setSyncInfo("")
    try {
      await getServerActionDrafts()
      const next = await syncOfflineDraftsNow()
      setDrafts(next)
      const accepted = next.filter((d) => d.sync_state === "accepted").length
      const rejected = next.filter((d) => d.sync_state === "rejected").length
      setSyncInfo(`Sync complete. accepted: ${accepted}, rejected: ${rejected}`)
    } catch (e) {
      const message = e instanceof Error ? e.message : "Sync failed."
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  function handleAddDraft() {
    setError("")
    setSyncInfo("")
    const result = addOfflineDraft({
      action_type: actionType,
      target_type: targetType,
      target_id: targetId,
      short_comment: shortComment,
      decision_status: decisionStatus,
    })
    if (!result.ok) {
      setError(result.reason)
      return
    }
    setDrafts(getOfflineDrafts())
    setShortComment("")
  }

  function handleClearRejected() {
    clearRejectedOfflineDrafts()
    setDrafts(getOfflineDrafts())
  }

  const orderedDrafts = useMemo(() => drafts, [drafts])

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Draft Queue</CardTitle>
        <CardDescription>
          Offline action drafts created on mobile — create, update, and sync pending decisions to the server. Drafts are not final until accepted by the server after sync.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
          Offline drafts are stored locally and are not final until synced and accepted by the server.
        </p>
        {!online ? (
          <p className="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
            Draft only. This action is not final until synced.
          </p>
        ) : null}
        {error ? <p className="text-xs text-destructive">{error}</p> : null}
        {syncInfo ? <p className="text-xs text-muted-foreground">{syncInfo}</p> : null}

        <div className="grid gap-2 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="mobile-draft-action-type" className="text-xs">
              action_type
            </Label>
            <Input
              id="mobile-draft-action-type"
              value={actionType}
              onChange={(e) => setActionType(e.target.value)}
              className="h-8 text-xs"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="mobile-draft-target-type" className="text-xs">
              target_type
            </Label>
            <Input
              id="mobile-draft-target-type"
              value={targetType}
              onChange={(e) => setTargetType(e.target.value)}
              className="h-8 text-xs"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="mobile-draft-target-id" className="text-xs">
              target_id
            </Label>
            <Input
              id="mobile-draft-target-id"
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              className="h-8 text-xs"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="mobile-draft-short-comment" className="text-xs">
              short comment
            </Label>
            <Input
              id="mobile-draft-short-comment"
              value={shortComment}
              onChange={(e) => setShortComment(e.target.value)}
              className="h-8 text-xs"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="mobile-draft-status" className="text-xs">
              decision/status
            </Label>
            <select
              id="mobile-draft-status"
              value={decisionStatus}
              onChange={(e) => setDecisionStatus(e.target.value as MobileDraftDecisionStatus)}
              className="flex h-8 w-full rounded-md border border-input bg-transparent px-2 text-xs"
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex min-w-0 flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" className="w-full sm:w-auto" onClick={handleAddDraft}>
            Add draft
          </Button>
          <Button type="button" size="sm" className="w-full sm:w-auto" onClick={() => void handleSyncNow()} disabled={!online || loading}>
            Sync now
          </Button>
          <Button type="button" size="sm" variant="outline" className="w-full sm:w-auto" onClick={handleClearRejected}>
            Clear rejected draft
          </Button>
        </div>

        {orderedDrafts.length === 0 ? (
          <p className="text-xs text-muted-foreground">No local drafts yet.</p>
        ) : (
          orderedDrafts.map((draft) => (
            <div key={draft.local_id} className="rounded-md border bg-muted/20 p-3">
              <p className="text-xs font-medium text-foreground">
                {draft.action_type} · {draft.target_type}:{draft.target_id}
              </p>
              <div className="mt-1 space-y-1 text-xs text-muted-foreground">
                <p>
                  <span className="font-medium text-foreground">decision/status:</span> {draft.decision_status}
                </p>
                <p>
                  <span className="font-medium text-foreground">timestamp:</span> {draft.timestamp}
                </p>
                <p>
                  <span className="font-medium text-foreground">sync:</span> {draft.sync_state}
                  {draft.sync_reason ? ` (${draft.sync_reason})` : ""}
                </p>
                <p>
                  <span className="font-medium text-foreground">comment:</span> {draft.short_comment || "—"}
                </p>
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  )
}

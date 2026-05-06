"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"

export type QualityOverrideDecision = "allow_with_warning" | "block" | "needs_reprocessing"

export type QualityOverridePayload = {
  reviewerName: string
  decision: QualityOverrideDecision
  reason: string
}

export type QualityOverrideDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (payload: QualityOverridePayload) => void | Promise<void>
  saveBusy?: boolean
}

const DECISION_LABELS: Record<QualityOverrideDecision, string> = {
  allow_with_warning: "Allow with warning (usable as evidence with caveats)",
  block: "Block (not usable as evidence until resolved)",
  needs_reprocessing: "Needs reprocessing",
}

export function QualityOverrideDialog({ open, onOpenChange, onSave, saveBusy = false }: QualityOverrideDialogProps) {
  const [reviewerName, setReviewerName] = useState("")
  const [decision, setDecision] = useState<QualityOverrideDecision>("allow_with_warning")
  const [reason, setReason] = useState("")

  useEffect(() => {
    if (open) {
      setReviewerName("")
      setDecision("allow_with_warning")
      setReason("")
    }
  }, [open])

  const reasonOk = reason.trim().length > 0
  const reviewerOk = reviewerName.trim().length > 0
  const canSave = reasonOk && reviewerOk && !saveBusy

  async function handleSave() {
    if (!canSave) return
    await onSave({
      reviewerName: reviewerName.trim(),
      decision,
      reason: reason.trim(),
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Quality override</DialogTitle>
          <DialogDescription>
            Record a reviewer decision when automated QC blocks progress or requires human review. Overrides must include a
            reason — silent overrides are not allowed. This records whether evidence remains{" "}
            <span className="font-medium text-foreground">usable as evidence</span> under stated conditions; it does not
            confirm structure or identity.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="qc-override-reviewer">Reviewer name</Label>
            <Input
              id="qc-override-reviewer"
              value={reviewerName}
              onChange={(e) => setReviewerName(e.target.value)}
              autoComplete="name"
              placeholder="Required"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="qc-override-decision">Decision</Label>
            <Select value={decision} onValueChange={(v) => setDecision(v as QualityOverrideDecision)}>
              <SelectTrigger id="qc-override-decision" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(DECISION_LABELS) as QualityOverrideDecision[]).map((key) => (
                  <SelectItem key={key} value={key}>
                    {DECISION_LABELS[key]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="qc-override-reason">Reason</Label>
            <Textarea
              id="qc-override-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={4}
              placeholder="Required — describe why this override is justified."
              className="min-h-[100px] resize-y"
            />
            {!reasonOk ? (
              <p className="text-xs text-muted-foreground">A reason is required before saving.</p>
            ) : null}
          </div>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saveBusy}>
            Cancel
          </Button>
          <Button type="button" onClick={() => void handleSave()} disabled={!canSave}>
            {saveBusy ? "Saving…" : "Save override"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

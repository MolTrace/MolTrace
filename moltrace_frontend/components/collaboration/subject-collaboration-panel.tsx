"use client"

// The four collaboration surfaces a filing or a campaign carries, in one card.
//
// They are four separate endpoints and four separate records, but to a reader they are one
// question — "what is happening on this record, and who is on it?" — so they are one
// section with tabs rather than four stacked cards competing for the same attention.
//
// Each tab loads its own rows when it is opened, so a tab nobody looks at costs nothing. A
// tab shows a count once it has loaded and has something outstanding; a tab with no count
// has not been opened yet and is not claiming to be empty.

import { useState } from "react"
import { Users } from "lucide-react"
import { ModuleCard, type ModuleCardAccent } from "@/components/dashboard/module-card"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { subjectKindLabel, type SubjectType } from "@/lib/collaboration/subject-collaboration"
import { SubjectApprovalsBody } from "@/components/collaboration/subject-approvals-panel"
import { SubjectCommentsBody } from "@/components/collaboration/subject-comments-panel"
import { SubjectReviewTasksBody } from "@/components/collaboration/subject-review-tasks-panel"
import { SubjectReviewersBody } from "@/components/collaboration/subject-reviewers-panel"

export type SubjectCollaborationPanelProps = {
  subjectType: SubjectType
  /** Null while the route param is still resolving, or when it is not a number. */
  subjectId: number | null
  accent?: ModuleCardAccent
  eyebrow?: string
}

/** Count shown on a tab, or nothing at all when that surface has not loaded yet. */
function TabCount({ count }: { count: number | null }) {
  if (count == null || count <= 0) return null
  return (
    <Badge variant="secondary" className="ml-1.5 px-1.5 py-0 text-[10px] tabular-nums">
      {count}
    </Badge>
  )
}

export function SubjectCollaborationPanel({
  subjectType,
  subjectId,
  accent = "teal",
  eyebrow = "Collaboration",
}: SubjectCollaborationPanelProps) {
  const kind = subjectKindLabel(subjectType)

  const [openTasks, setOpenTasks] = useState<number | null>(null)
  const [unresolvedComments, setUnresolvedComments] = useState<number | null>(null)
  const [pendingReviewers, setPendingReviewers] = useState<number | null>(null)

  return (
    <ModuleCard
      accent={accent}
      eyebrow={eyebrow}
      icon={Users}
      title="Work on this together"
      description={`Review tasks, notes, sign-off decisions and reviewer nominations for this ${kind}. Everyone who can open this ${kind} sees the same four.`}
    >
      <Tabs defaultValue="tasks">
        <TabsList className="h-auto w-full flex-wrap justify-start">
          <TabsTrigger value="tasks">
            Review tasks
            <TabCount count={openTasks} />
          </TabsTrigger>
          <TabsTrigger value="comments">
            Notes
            <TabCount count={unresolvedComments} />
          </TabsTrigger>
          <TabsTrigger value="approvals">Sign-off</TabsTrigger>
          <TabsTrigger value="reviewers">
            Reviewers
            <TabCount count={pendingReviewers} />
          </TabsTrigger>
        </TabsList>

        <TabsContent value="tasks" className="mt-4">
          <SubjectReviewTasksBody
            subjectType={subjectType}
            subjectId={subjectId}
            onAttentionCountChange={setOpenTasks}
          />
        </TabsContent>
        <TabsContent value="comments" className="mt-4">
          <SubjectCommentsBody
            subjectType={subjectType}
            subjectId={subjectId}
            onAttentionCountChange={setUnresolvedComments}
          />
        </TabsContent>
        <TabsContent value="approvals" className="mt-4">
          <SubjectApprovalsBody subjectType={subjectType} subjectId={subjectId} />
        </TabsContent>
        <TabsContent value="reviewers" className="mt-4">
          <SubjectReviewersBody
            subjectType={subjectType}
            subjectId={subjectId}
            onAttentionCountChange={setPendingReviewers}
          />
        </TabsContent>
      </Tabs>
    </ModuleCard>
  )
}

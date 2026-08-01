"use client"

import { usePathname } from "next/navigation"
import {
  WorkspaceStageNav,
  type WorkspaceStageGroup,
} from "@/components/app/workspace-stage-nav"

/**
 * Module-level navigation across Regentry's seven top-level destinations.
 *
 * Unlike SpectraCheck and the dossier — where the sections are panels in one
 * page — these are separate routes, and there was no way to get from one to
 * another: you had to go back to the Regentry landing page and pick again from
 * a row of buttons. The same two-tier grouping applies, so the module reads
 * like the others; the sections just navigate instead of switching panels.
 *
 * Detail routes (a single dossier, change, or source) deliberately do not match
 * any section — they carry their own workspace nav, and highlighting a parent
 * here would claim you were on the list page when you are not.
 */
const REGENTRY_NAV: WorkspaceStageGroup[] = [
  {
    id: "overview",
    label: "Overview",
    sections: [
      {
        value: "/regulatory",
        label: "Overview",
        desc: "Dossiers, review workload, and the next actions waiting on your team.",
        href: "/regulatory",
      },
    ],
  },
  {
    id: "assessment",
    label: "Assessment",
    sections: [
      {
        value: "/regulatory/impurities",
        label: "Impurity assessment",
        desc: "Assess impurities, residual solvents, and nitrosamine risk against the limits that apply.",
        href: "/regulatory/impurities",
      },
    ],
  },
  {
    id: "actions",
    label: "Actions",
    sections: [
      {
        value: "/regulatory/action-queue",
        label: "Action queue",
        desc: "Open regulatory work across every dossier, by severity and owner.",
        href: "/regulatory/action-queue",
      },
      {
        value: "/regulatory/notifications",
        label: "Notifications",
        desc: "Change alerts, dossier updates, and review triggers awaiting triage.",
        href: "/regulatory/notifications",
      },
    ],
  },
  {
    id: "surveillance",
    label: "Surveillance",
    sections: [
      {
        value: "/regulatory/surveillance",
        label: "Surveillance",
        desc: "External rule changes detected, and which dossiers each one touches.",
        href: "/regulatory/surveillance",
      },
      {
        value: "/regulatory/rule-updates",
        label: "Rule updates",
        desc: "Proposed rule-set changes waiting for review before they take effect.",
        href: "/regulatory/rule-updates",
      },
      {
        value: "/regulatory/sources",
        label: "Source library",
        desc: "The regulatory source documents this workspace cites and monitors for change.",
        href: "/regulatory/sources",
      },
    ],
  },
]

/**
 * Mounted only on the seven list routes above, so the path always matches one of
 * them. Detail routes render nothing here on purpose: they are not their list
 * page, and the nav falls back to marking the first stage current when nothing
 * matches — which on a detail page would claim you were somewhere you are not.
 */
export function RegentryModuleNav() {
  const pathname = usePathname()
  const known = REGENTRY_NAV.flatMap((g) => g.sections).some((s) => s.value === pathname)
  if (!known) return null

  // Owns its own bottom margin: the shell's <main> lays children out with no
  // gap, and each of the seven workspaces starts straight in with its heading.
  return (
    <div className="mb-6">
      <WorkspaceStageNav
        groups={REGENTRY_NAV}
        activeValue={pathname}
        label="Regentry"
        accent="cyan"
      />
    </div>
  )
}

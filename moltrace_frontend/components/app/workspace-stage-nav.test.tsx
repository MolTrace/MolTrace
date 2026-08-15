import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { describe, expect, it, vi } from "vitest"

import {
  WorkspaceStageNav,
  type WorkspaceStageGroup,
} from "@/components/app/workspace-stage-nav"

const GROUPS: WorkspaceStageGroup[] = [
  {
    id: "session",
    label: "Session",
    sections: [{ value: "tab-session", label: "Session", desc: "Project and sample context." }],
  },
  {
    id: "start",
    label: "Overview",
    sections: [
      { value: "tab-overview", label: "Overview", desc: "Summary of available evidence." },
      { value: "tab-workflow", label: "Workflow", desc: "A predefined sequence of steps." },
    ],
  },
  {
    id: "inputs",
    label: "Evidence Inputs",
    sections: [
      { value: "tab-nmr-text", label: "NMR text + candidates", desc: "Enter candidate structures." },
      { value: "tab-processed", label: "Processed 1H / 13C upload", desc: "CSV, TSV, TXT, or JCAMP-DX." },
    ],
  },
  {
    id: "developer",
    label: "Developer",
    sections: [{ value: "tab-dev-json", label: "Developer JSON", desc: "Raw results." }],
  },
]

function Harness({ initial = "tab-overview" }: { initial?: string }) {
  const [value, setValue] = useState(initial)
  return <WorkspaceStageNav groups={GROUPS} activeValue={value} onSelect={setValue} label="Test" />
}

describe("WorkspaceStageNav", () => {
  it("shows every stage, and only the active stage's sections", () => {
    render(<Harness />)

    expect(screen.getByTestId("stage-start")).toHaveAttribute("aria-selected", "true")
    expect(screen.getByTestId("stage-inputs")).toHaveAttribute("aria-selected", "false")

    // Sections of the active stage only — the other stage's are not rendered.
    expect(screen.getByTestId("stage-section-tab-overview")).toBeInTheDocument()
    expect(screen.getByTestId("stage-section-tab-workflow")).toBeInTheDocument()
    expect(screen.queryByTestId("stage-section-tab-nmr-text")).not.toBeInTheDocument()
  })

  it("derives the active stage from the active section, so deep links land correctly", () => {
    render(<Harness initial="tab-processed" />)

    expect(screen.getByTestId("stage-inputs")).toHaveAttribute("aria-selected", "true")
    expect(screen.getByTestId("stage-section-tab-processed")).toHaveAttribute("aria-selected", "true")
  })

  it("opens a stage's first section when that stage has not been visited", async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.click(screen.getByTestId("stage-inputs"))

    expect(screen.getByTestId("stage-section-tab-nmr-text")).toHaveAttribute("aria-selected", "true")
    expect(screen.getByText("Enter candidate structures.")).toBeInTheDocument()
  })

  it("returns to the section a reader last used in that stage", async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.click(screen.getByTestId("stage-inputs"))
    await user.click(screen.getByTestId("stage-section-tab-processed"))
    await user.click(screen.getByTestId("stage-start"))
    await user.click(screen.getByTestId("stage-inputs"))

    expect(screen.getByTestId("stage-section-tab-processed")).toHaveAttribute("aria-selected", "true")
  })

  it("omits the section row for a stage that has only one section", async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.click(screen.getByTestId("stage-developer"))

    expect(screen.getByTestId("stage-developer")).toHaveAttribute("aria-selected", "true")
    expect(screen.queryByRole("tablist", { name: "Developer sections" })).not.toBeInTheDocument()
    expect(screen.getByText("Raw results.")).toBeInTheDocument()
  })

  it("moves between stages with the arrow keys", async () => {
    const user = userEvent.setup()
    render(<Harness />)

    screen.getByTestId("stage-start").focus()
    await user.keyboard("{ArrowRight}")

    expect(screen.getByTestId("stage-inputs")).toHaveAttribute("aria-selected", "true")
  })

  it("puts Session first, ahead of Overview", () => {
    render(<Harness />)

    const stages = screen
      .getAllByRole("tab")
      .filter((el) => el.getAttribute("data-testid")?.startsWith("stage-"))
      .map((el) => el.getAttribute("data-testid"))

    expect(stages[0]).toBe("stage-session")
    expect(stages[1]).toBe("stage-start")
  })

  it("moves between sections of the active stage with the arrow keys", async () => {
    const user = userEvent.setup()
    render(<Harness />)

    screen.getByTestId("stage-section-tab-overview").focus()
    await user.keyboard("{ArrowRight}")

    expect(screen.getByTestId("stage-section-tab-workflow")).toHaveAttribute("aria-selected", "true")
  })

  it("labels a stage with its name alone — a number would read as a task count", () => {
    render(<Harness />)

    expect(screen.getByTestId("stage-inputs").textContent?.trim()).toBe("Evidence Inputs")
    expect(screen.getByTestId("stage-start").textContent?.trim()).toBe("Overview")
  })

  it("selects a stage without losing the caller's control of state", async () => {
    const onSelect = vi.fn()
    const user = userEvent.setup()
    render(
      <WorkspaceStageNav groups={GROUPS} activeValue="tab-overview" onSelect={onSelect} label="Test" />,
    )

    await user.click(screen.getByTestId("stage-inputs"))

    expect(onSelect).toHaveBeenCalledWith("tab-nmr-text")
  })
})

describe("WorkspaceStageNav route mode", () => {
  const ROUTE_GROUPS: WorkspaceStageGroup[] = [
    {
      id: "overview",
      label: "Overview",
      sections: [
        { value: "/regulatory", label: "Overview", desc: "Dossiers and workload.", href: "/regulatory" },
      ],
    },
    {
      id: "actions",
      label: "Actions",
      sections: [
        {
          value: "/regulatory/action-queue",
          label: "Action queue",
          desc: "Open regulatory work.",
          href: "/regulatory/action-queue",
        },
        {
          value: "/regulatory/notifications",
          label: "Notifications",
          desc: "Change alerts awaiting triage.",
          href: "/regulatory/notifications",
        },
      ],
    },
  ]

  it("renders links, not tabs, when sections carry an href", () => {
    render(
      <WorkspaceStageNav
        groups={ROUTE_GROUPS}
        activeValue="/regulatory/action-queue"
        label="Regentry"
      />,
    )

    // These are page loads; calling them tabs would promise panel switching.
    expect(screen.queryAllByRole("tab")).toHaveLength(0)
    const stage = screen.getByTestId("stage-actions")
    expect(stage.tagName).toBe("A")
    expect(stage).toHaveAttribute("href", "/regulatory/action-queue")
  })

  it("marks the current page with aria-current in both tiers", () => {
    render(
      <WorkspaceStageNav
        groups={ROUTE_GROUPS}
        activeValue="/regulatory/notifications"
        label="Regentry"
      />,
    )

    expect(screen.getByTestId("stage-actions")).toHaveAttribute("aria-current", "page")
    expect(screen.getByTestId("stage-overview")).not.toHaveAttribute("aria-current")
    expect(screen.getByTestId("stage-section-/regulatory/notifications")).toHaveAttribute(
      "aria-current",
      "page",
    )
    expect(screen.getByTestId("stage-section-/regulatory/action-queue")).not.toHaveAttribute(
      "aria-current",
    )
  })

  it("points each stage at its own first route", () => {
    render(<WorkspaceStageNav groups={ROUTE_GROUPS} activeValue="/regulatory" label="Regentry" />)

    expect(screen.getByTestId("stage-overview")).toHaveAttribute("href", "/regulatory")
    expect(screen.getByTestId("stage-actions")).toHaveAttribute("href", "/regulatory/action-queue")
    // Single-section stage: no second row to choose from.
    expect(screen.queryByTestId("stage-section-/regulatory")).not.toBeInTheDocument()
  })
})

/**
 * LAYOUT STABILITY.
 *
 * The second tier only has pills when the active stage holds more than one
 * section, so on a nav whose stages hold different numbers — Regentry is 1, 1, 2
 * and 3 — the nav changed height as you moved between them. It sits above the
 * whole workspace, so everything below jumped. Measured on Regentry at
 * 1440x900: 80px against 136px, a 56px shift on every stage change. That is
 * what "the UI is shaky" was.
 *
 * Four of the five navs in the app had mixed stage sizes and all four were
 * doing it: Regentry, SpectraCheck, the dossier workspace and Reaction Studio.
 *
 * jsdom has no layout, so these assert the RESERVATIONS rather than pixel
 * heights — the classes are the mechanism, and the pixels were verified in a
 * real browser. A test that measured heights here would read 0 for everything
 * and pass no matter what.
 */
describe("WorkspaceStageNav — layout stability", () => {
  const MIXED: WorkspaceStageGroup[] = [
    { id: "one", label: "One", sections: [{ value: "a", label: "A", desc: "Short." }] },
    {
      id: "many",
      label: "Many",
      sections: [
        { value: "b", label: "B", desc: "Another." },
        { value: "c", label: "C", desc: "And another." },
      ],
    },
  ]

  // An explicit hook, not `.min-h-11`: the primary tabs carry that same utility
  // class, so selecting on it matched a tab button and the "reserves nothing"
  // case passed for the wrong reason.
  const reservedBand = (c: HTMLElement) => c.querySelector("[data-stage-sections-band]")

  it("reserves the second-tier band on a stage that has no pills", () => {
    // The single-section stage. Without the reservation this row is absent and
    // the nav is shorter here than on every other stage.
    const { container } = render(
      <WorkspaceStageNav groups={MIXED} activeValue="a" label="Test" onSelect={() => {}} />,
    )
    const band = reservedBand(container)
    expect(band).not.toBeNull()
    // Existing is not enough: an empty band with no min-height is 0px tall and
    // the jump is back. Mutation-checked — dropping the class alone used to
    // leave this test green.
    expect(band!.className).toContain("min-h-11")
    // ...and it is still EMPTY — the fix reserves space, it does not invent a
    // pill duplicating the tab you are already on.
    expect(container.querySelector('[aria-label$="sections"]')).toBeNull()
  })

  it("uses the same band on a stage that does have pills", () => {
    const { container } = render(
      <WorkspaceStageNav groups={MIXED} activeValue="b" label="Test" onSelect={() => {}} />,
    )
    const band = reservedBand(container)
    expect(band).not.toBeNull()
    // Same reserved height as the empty case, or the two states differ by the
    // 4px of `pb-1` that box-sizing folds inside an empty reservation.
    expect(band!.className).toContain("min-h-11")
    expect(container.querySelector('[aria-label$="sections"]')).not.toBeNull()
  })

  it("reserves nothing when no stage could ever show a second tier", () => {
    // Every stage single-section: the row can never appear, so reserving room
    // for it would be dead space that nothing ever fills.
    const uniform: WorkspaceStageGroup[] = [
      { id: "x", label: "X", sections: [{ value: "x1", label: "X1", desc: "One." }] },
      { id: "y", label: "Y", sections: [{ value: "y1", label: "Y1", desc: "Two." }] },
    ]
    const { container } = render(
      <WorkspaceStageNav groups={uniform} activeValue="x1" label="Test" onSelect={() => {}} />,
    )
    expect(reservedBand(container)).toBeNull()
  })

  it("reserves two lines for the description, which is 1 or 2 lines by section", () => {
    // Regentry's descriptions measured 20px and 40px depending on the section,
    // so the block below them moved 20px on every switch even when the pill row
    // did not change.
    const { container } = render(
      <WorkspaceStageNav groups={MIXED} activeValue="a" label="Test" onSelect={() => {}} />,
    )
    const desc = container.querySelector("p.max-w-3xl")
    expect(desc).not.toBeNull()
    expect(desc!.className).toContain("mt-two-line-slot")
  })
})

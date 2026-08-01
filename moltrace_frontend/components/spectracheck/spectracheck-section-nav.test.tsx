import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { describe, expect, it, vi } from "vitest"

import {
  SpectraCheckSectionNav,
  type SpectraNavGroup,
} from "@/components/spectracheck/spectracheck-section-nav"

const GROUPS: SpectraNavGroup[] = [
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
  return <SpectraCheckSectionNav groups={GROUPS} activeValue={value} onSelect={setValue} />
}

describe("SpectraCheckSectionNav", () => {
  it("shows every stage, and only the active stage's sections", () => {
    render(<Harness />)

    expect(screen.getByTestId("spectracheck-stage-start")).toHaveAttribute("aria-selected", "true")
    expect(screen.getByTestId("spectracheck-stage-inputs")).toHaveAttribute("aria-selected", "false")

    // Sections of the active stage only — the other stage's are not rendered.
    expect(screen.getByTestId("spectracheck-tab-tab-overview")).toBeInTheDocument()
    expect(screen.getByTestId("spectracheck-tab-tab-workflow")).toBeInTheDocument()
    expect(screen.queryByTestId("spectracheck-tab-tab-nmr-text")).not.toBeInTheDocument()
  })

  it("derives the active stage from the active section, so deep links land correctly", () => {
    render(<Harness initial="tab-processed" />)

    expect(screen.getByTestId("spectracheck-stage-inputs")).toHaveAttribute("aria-selected", "true")
    expect(screen.getByTestId("spectracheck-tab-tab-processed")).toHaveAttribute("aria-selected", "true")
  })

  it("opens a stage's first section when that stage has not been visited", async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.click(screen.getByTestId("spectracheck-stage-inputs"))

    expect(screen.getByTestId("spectracheck-tab-tab-nmr-text")).toHaveAttribute("aria-selected", "true")
    expect(screen.getByText("Enter candidate structures.")).toBeInTheDocument()
  })

  it("returns to the section a reader last used in that stage", async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.click(screen.getByTestId("spectracheck-stage-inputs"))
    await user.click(screen.getByTestId("spectracheck-tab-tab-processed"))
    await user.click(screen.getByTestId("spectracheck-stage-start"))
    await user.click(screen.getByTestId("spectracheck-stage-inputs"))

    expect(screen.getByTestId("spectracheck-tab-tab-processed")).toHaveAttribute("aria-selected", "true")
  })

  it("omits the section row for a stage that has only one section", async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.click(screen.getByTestId("spectracheck-stage-developer"))

    expect(screen.getByTestId("spectracheck-stage-developer")).toHaveAttribute("aria-selected", "true")
    expect(screen.queryByRole("tablist", { name: "Developer sections" })).not.toBeInTheDocument()
    expect(screen.getByText("Raw results.")).toBeInTheDocument()
  })

  it("moves between stages with the arrow keys", async () => {
    const user = userEvent.setup()
    render(<Harness />)

    screen.getByTestId("spectracheck-stage-start").focus()
    await user.keyboard("{ArrowRight}")

    expect(screen.getByTestId("spectracheck-stage-inputs")).toHaveAttribute("aria-selected", "true")
  })

  it("puts Session first, ahead of Overview", () => {
    render(<Harness />)

    const stages = screen
      .getAllByRole("tab")
      .filter((el) => el.getAttribute("data-testid")?.startsWith("spectracheck-stage-"))
      .map((el) => el.getAttribute("data-testid"))

    expect(stages[0]).toBe("spectracheck-stage-session")
    expect(stages[1]).toBe("spectracheck-stage-start")
  })

  it("moves between sections of the active stage with the arrow keys", async () => {
    const user = userEvent.setup()
    render(<Harness />)

    screen.getByTestId("spectracheck-tab-tab-overview").focus()
    await user.keyboard("{ArrowRight}")

    expect(screen.getByTestId("spectracheck-tab-tab-workflow")).toHaveAttribute("aria-selected", "true")
  })

  it("labels a stage with its name alone — a number would read as a task count", () => {
    render(<Harness />)

    expect(screen.getByTestId("spectracheck-stage-inputs").textContent?.trim()).toBe("Evidence Inputs")
    expect(screen.getByTestId("spectracheck-stage-start").textContent?.trim()).toBe("Overview")
  })

  it("selects a stage without losing the caller's control of state", async () => {
    const onSelect = vi.fn()
    const user = userEvent.setup()
    render(
      <SpectraCheckSectionNav groups={GROUPS} activeValue="tab-overview" onSelect={onSelect} />,
    )

    await user.click(screen.getByTestId("spectracheck-stage-inputs"))

    expect(onSelect).toHaveBeenCalledWith("tab-nmr-text")
  })
})

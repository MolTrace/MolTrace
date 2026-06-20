import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { StatusBadge } from "@/components/ui/status-badge"

describe("StatusBadge", () => {
  it("renders a humanized label and keeps the raw value in the title", () => {
    render(<StatusBadge status="ready_for_qa_review" />)
    const el = screen.getByText("Ready for QA review")
    expect(el).toBeInTheDocument()
    expect(el).toHaveAttribute("title", "ready_for_qa_review")
  })

  it("renders an em dash for an empty status", () => {
    render(<StatusBadge status={null} />)
    expect(screen.getByText("—")).toBeInTheDocument()
  })
})

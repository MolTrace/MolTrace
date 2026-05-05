import { describe, expect, it } from "vitest"
import { render, screen, within } from "@testing-library/react"
import { FragmentTreeViewer } from "@/src/components/science/FragmentTreeViewer"

describe("FragmentTreeViewer", () => {
  it("renders nodes and edges", () => {
    render(
      <FragmentTreeViewer
        title="Test tree"
        nodes={[
          { id: "prec", mz: 300.1, label: "Prec", intensity: 100 },
          { id: "a", mz: 200.05, intensity: 40 },
          { id: "b", mz: 150.02, intensity: 20 },
        ]}
        edges={[
          { source: "prec", target: "a", loss: "H2O", delta_mz: 18.01 },
          { source: "a", target: "b", loss: "CH2O" },
        ]}
      />
    )

    const root = screen.getByTestId("fragment-tree-viewer-root")
    expect(root).toBeInTheDocument()
    expect(screen.getByText("Test tree")).toBeInTheDocument()

    const svg = root.querySelector('svg[role="img"]')
    expect(svg).toBeTruthy()
    expect(within(svg as HTMLElement).getByText(/H2O ·/)).toBeInTheDocument()
    expect(within(svg as HTMLElement).getByText(/Δm\/z 18/)).toBeInTheDocument()

    expect(screen.getByText("Diagnostic fragment hits")).toBeInTheDocument()
    expect(within(svg as HTMLElement).getByText("300.1000")).toBeInTheDocument()
  })

  it("renders contradiction edge", () => {
    render(
      <FragmentTreeViewer
        nodes={[
          { id: "p", mz: 100 },
          { id: "c", mz: 50 },
        ]}
        edges={[{ source: "p", target: "c", loss: "?", contradiction: true }]}
      />
    )
    const contradictGroups = document.querySelectorAll("[data-contradiction=\"1\"]")
    expect(contradictGroups.length).toBeGreaterThan(0)
  })

  it("handles missing nodes gracefully", () => {
    render(
      <FragmentTreeViewer
        nodes={[{ id: "only", mz: 123.45 }]}
        edges={[
          { source: "ghost", target: "only", loss: "bad" },
          { source: "only", target: "missing", loss: "also bad" },
        ]}
      />
    )

    expect(screen.getByText(/unknown source/i)).toBeInTheDocument()
    expect(screen.getByText(/unknown target/i)).toBeInTheDocument()
    expect(screen.queryByText("bad")).not.toBeInTheDocument()
  })
})

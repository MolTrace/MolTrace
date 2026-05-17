import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

import { ResetToExampleButton } from "@/components/spectracheck/spectracheck-reset-to-example-button"

const DEFAULT_PROTON =
  "1H NMR (400 MHz, CDCl3) δ 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"

describe("ResetToExampleButton", () => {
  it("renders nothing when current matches fallback (default state)", () => {
    const { container } = render(
      <ResetToExampleButton
        current={DEFAULT_PROTON}
        fallback={DEFAULT_PROTON}
        onReset={() => {}}
        testId="x"
      />,
    )
    expect(container.firstChild).toBeNull()
  })

  it("renders nothing when both current and fallback are empty", () => {
    const { container } = render(
      <ResetToExampleButton current="" fallback="" onReset={() => {}} testId="x" />,
    )
    expect(container.firstChild).toBeNull()
  })

  it("renders the button when current differs from fallback", () => {
    render(
      <ResetToExampleButton
        current="my custom 1H NMR text"
        fallback={DEFAULT_PROTON}
        onReset={() => {}}
        testId="proton-reset"
      />,
    )
    expect(screen.getByTestId("proton-reset")).toBeInTheDocument()
    expect(screen.getByText(/Reset to example/i)).toBeInTheDocument()
  })

  it("renders when the user has cleared the field (current is empty, fallback is not)", () => {
    render(
      <ResetToExampleButton
        current=""
        fallback={DEFAULT_PROTON}
        onReset={() => {}}
        testId="proton-reset"
      />,
    )
    expect(screen.getByTestId("proton-reset")).toBeInTheDocument()
  })

  it("treats whitespace-only differences as 'equal' (no button)", () => {
    // ``"  text  "`` and ``"text"`` should not be considered different just
    // because of leading/trailing spaces — that would surface a Reset button
    // on a field that the user perceives as identical to the default.
    const { container } = render(
      <ResetToExampleButton
        current={`   ${DEFAULT_PROTON}\n  `}
        fallback={DEFAULT_PROTON}
        onReset={() => {}}
        testId="x"
      />,
    )
    expect(container.firstChild).toBeNull()
  })

  it("calls onReset exactly once when clicked", async () => {
    const onReset = vi.fn()
    const user = userEvent.setup()
    render(
      <ResetToExampleButton
        current="my edited text"
        fallback={DEFAULT_PROTON}
        onReset={onReset}
        testId="proton-reset"
      />,
    )
    await user.click(screen.getByTestId("proton-reset"))
    expect(onReset).toHaveBeenCalledTimes(1)
  })

  it("honors custom title attribute for hover tooltip", () => {
    render(
      <ResetToExampleButton
        current="changed"
        fallback={DEFAULT_PROTON}
        onReset={() => {}}
        testId="proton-reset"
        title="Restore the bundled 1H NMR example"
      />,
    )
    const btn = screen.getByTestId("proton-reset")
    expect(btn).toHaveAttribute("title", "Restore the bundled 1H NMR example")
  })

  it("honors custom label override", () => {
    render(
      <ResetToExampleButton
        current="changed"
        fallback={DEFAULT_PROTON}
        onReset={() => {}}
        testId="x"
        label="Restore defaults"
      />,
    )
    expect(screen.getByText("Restore defaults")).toBeInTheDocument()
  })
})

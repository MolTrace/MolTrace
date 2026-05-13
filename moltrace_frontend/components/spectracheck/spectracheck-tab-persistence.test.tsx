/**
 * Integration: verifies that SpectraCheck section UI state (uploaded files,
 * preview/process results, errors) survives when the section component is
 * unmounted and remounted — the exact scenario triggered by Radix's
 * `TabsContent` swapping which tab is active.
 */

import { describe, expect, it } from "vitest"
import { fireEvent, render } from "@testing-library/react"
import { SpectraCheckTabStateProvider } from "@/components/spectracheck/spectracheck-tab-state-context"
import { SpectraCheckRawFidSection } from "@/components/spectracheck/spectracheck-raw-fid-section"
import { SpectraCheckProcessedSpectrumSection } from "@/components/spectracheck/spectracheck-processed-spectrum-section"

function Frame({
  showRaw,
  showProcessed,
}: {
  showRaw: boolean
  showProcessed: boolean
}) {
  return (
    <SpectraCheckTabStateProvider>
      {showRaw ? (
        <SpectraCheckRawFidSection sampleId="t1" onSampleIdChange={() => {}} solvent="CDCl3" />
      ) : null}
      {showProcessed ? (
        <SpectraCheckProcessedSpectrumSection
          sampleId="t1"
          onSampleIdChange={() => {}}
          solvent="CDCl3"
          candidatesText="A | CCO"
        />
      ) : null}
    </SpectraCheckTabStateProvider>
  )
}

describe("SpectraCheck tab state persistence (provider-wrapped)", () => {
  it("retains the raw FID selected file name after a remount", () => {
    const { rerender, queryByText } = render(<Frame showRaw showProcessed={false} />)

    // Drop a file into the raw FID drop zone.
    const file = new File(["pretend-fid"], "trace.zip", { type: "application/zip" })
    const dropZone = document.querySelector('[aria-label^="Drop raw FID archive"]') as HTMLElement
    expect(dropZone).not.toBeNull()
    fireEvent.drop(dropZone, {
      dataTransfer: { files: [file], types: ["Files"] },
    } as unknown as Event)

    expect(queryByText("trace.zip")).not.toBeNull()

    // Simulate switching to a different tab — the section unmounts.
    rerender(<Frame showRaw={false} showProcessed />)
    expect(queryByText("trace.zip")).toBeNull()

    // And back — the section remounts; the file name should still be there.
    rerender(<Frame showRaw showProcessed={false} />)
    expect(queryByText("trace.zip")).not.toBeNull()
  })

  it("retains the processed selected file name after a remount", () => {
    const { rerender, queryByText } = render(<Frame showRaw={false} showProcessed />)
    const file = new File(["pretend-spec"], "spec.jdx", { type: "text/plain" })
    const dropZone = document.querySelector('[aria-label^="Drop processed spectrum file"]') as HTMLElement
    expect(dropZone).not.toBeNull()
    fireEvent.drop(dropZone, {
      dataTransfer: { files: [file], types: ["Files"] },
    } as unknown as Event)

    expect(queryByText("spec.jdx")).not.toBeNull()

    rerender(<Frame showRaw showProcessed={false} />)
    expect(queryByText("spec.jdx")).toBeNull()

    rerender(<Frame showRaw={false} showProcessed />)
    expect(queryByText("spec.jdx")).not.toBeNull()
  })
})

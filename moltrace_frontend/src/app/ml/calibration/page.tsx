import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { MlCalibrationWorkspace } from "@/components/ml/ml-calibration-workspace"

export default function MlCalibrationPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading calibration…</div>}>
        <MlCalibrationWorkspace />
      </Suspense>
    </AppShell>
  )
}

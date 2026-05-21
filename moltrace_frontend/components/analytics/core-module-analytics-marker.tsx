"use client"

import { useEffect } from "react"
import {
  trackCoreModuleOpened,
  type CoreAnalyticsModule,
} from "@/src/lib/analytics/analytics-client"

type CoreModuleAnalyticsMarkerProps = {
  module: CoreAnalyticsModule
  surface?: string
}

export function CoreModuleAnalyticsMarker({ module, surface }: CoreModuleAnalyticsMarkerProps) {
  useEffect(() => {
    trackCoreModuleOpened(module, {
      surface: surface ?? module,
    })
  }, [module, surface])

  return null
}

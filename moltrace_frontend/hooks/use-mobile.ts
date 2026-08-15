import * as React from 'react'
import { applyShellMode, computeShellMode } from '@/src/lib/shell/shell-mode'

const MOBILE_BREAKPOINT = 768

/**
 * The shell decision itself lives in src/lib/shell/shell-mode.ts, because a
 * blocking <head> script has to make the SAME call before React exists — see
 * that file. Duplicating the predicate here is how the two would drift.
 */
function isMobileViewport() {
  if (typeof window === 'undefined') return false
  return computeShellMode(window) === 'mobile'
}

// False only until the first mount anywhere has completed. On the true first
// page load the initial render must match the server-rendered HTML (which was
// built with `false`) or React hydrates into a mismatch — but every LATER mount
// is a client-side navigation with no hydration constraint, and starting those
// at `false` made phones mount desktop trees for a tick (effects included).
// Same contract ResponsiveAppShell documents for its preference cache.
let hydrationComplete = false

export function useIsMobile() {
  const [isMobile, setIsMobile] = React.useState(
    () => hydrationComplete && isMobileViewport(),
  )

  React.useEffect(() => {
    hydrationComplete = true
  }, [])

  React.useEffect(() => {
    const queries =
      typeof window.matchMedia === 'function'
        ? [
            window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`),
            window.matchMedia('(pointer: coarse)'),
            window.matchMedia('(hover: none)'),
          ]
        : []
    const onChange = () => {
      const mobile = isMobileViewport()
      setIsMobile(mobile)
      // The pre-paint script set this; keep it true as the viewport changes so
      // the CSS half of the decision never lags the React half.
      applyShellMode(mobile ? 'mobile' : 'desktop')
    }

    // No addListener fallback: the declared browser floor (package.json
    // browserslist — Tailwind v4's floor, Safari ≥ 16.4) is far past the
    // Safari ≤ 13 the old guard defended. On those browsers the oklch()/
    // @custom-variant stylesheet does not even parse, so the guard was
    // unreachable support theater.
    queries.forEach((mql) => mql.addEventListener('change', onChange))
    window.addEventListener('resize', onChange)
    onChange()

    return () => {
      queries.forEach((mql) => mql.removeEventListener('change', onChange))
      window.removeEventListener('resize', onChange)
    }
  }, [])

  return isMobile
}

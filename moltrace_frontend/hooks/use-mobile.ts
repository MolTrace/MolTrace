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

    // Older Safari (≤13) ships MediaQueryList without add/removeEventListener —
    // only the deprecated addListener pair. Guard so the hook degrades to the
    // resize listener instead of throwing and unmounting the page.
    queries.forEach((mql) => {
      if (typeof mql.addEventListener === 'function') mql.addEventListener('change', onChange)
      else if (typeof mql.addListener === 'function') mql.addListener(onChange)
    })
    window.addEventListener('resize', onChange)
    onChange()

    return () => {
      queries.forEach((mql) => {
        if (typeof mql.removeEventListener === 'function') mql.removeEventListener('change', onChange)
        else if (typeof mql.removeListener === 'function') mql.removeListener(onChange)
      })
      window.removeEventListener('resize', onChange)
    }
  }, [])

  return isMobile
}

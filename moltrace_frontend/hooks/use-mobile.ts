import * as React from 'react'

const MOBILE_BREAKPOINT = 768
const MOBILE_USER_AGENT =
  /Android|webOS|iPhone|iPad|iPod|BlackBerry|BB10|IEMobile|Opera Mini|Mobile|Tablet/i
const DESKTOP_PLATFORM = /Mac|Win|Linux x86|Linux i686|Linux armv|CrOS|X11/i

function mediaMatches(query: string) {
  return typeof window.matchMedia === 'function' && window.matchMedia(query).matches
}

function isDesktopPlatform() {
  const nav = window.navigator
  const userAgentData = nav as Navigator & { userAgentData?: { platform?: string; mobile?: boolean } }
  const platform = userAgentData.userAgentData?.platform || nav.platform || ''
  const ua = nav.userAgent || ''

  if (userAgentData.userAgentData?.mobile === true) return false
  if (/Mac/i.test(platform) && nav.maxTouchPoints > 1 && /Mobile|Safari/i.test(ua)) return false
  return DESKTOP_PLATFORM.test(platform) && !MOBILE_USER_AGENT.test(ua)
}

function isMobileViewport() {
  if (typeof window === 'undefined') return false
  if (isDesktopPlatform()) return false

  const isNarrow = window.innerWidth < MOBILE_BREAKPOINT
  const hasCoarsePointer =
    mediaMatches('(pointer: coarse)') || window.navigator.maxTouchPoints > 0
  const hasNoHover = mediaMatches('(hover: none)')
  const hasModernPointerSignals =
    typeof window.matchMedia === 'function' &&
    (mediaMatches('(pointer: coarse)') || mediaMatches('(pointer: fine)') || mediaMatches('(hover: none)') || mediaMatches('(hover: hover)'))
  const looksMobileByAgent = MOBILE_USER_AGENT.test(window.navigator.userAgent || '')

  return isNarrow && (hasModernPointerSignals ? hasCoarsePointer && hasNoHover : looksMobileByAgent)
}

export function useIsMobile() {
  const [isMobile, setIsMobile] = React.useState(false)

  React.useEffect(() => {
    const queries =
      typeof window.matchMedia === 'function'
        ? [
            window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`),
            window.matchMedia('(pointer: coarse)'),
            window.matchMedia('(hover: none)'),
          ]
        : []
    const onChange = () => setIsMobile(isMobileViewport())

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

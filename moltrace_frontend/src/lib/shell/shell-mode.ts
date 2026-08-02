/**
 * Which shell a browser should get, decided once — before first paint.
 *
 * The app picks between a desktop sidebar and a mobile bottom bar. `useIsMobile`
 * makes that call, but a React hook cannot run until hydration, and it starts by
 * assuming desktop. On a phone that assumption is wrong for a frame, so the full
 * desktop sidebar paints and is then torn away — the most visible layout shift
 * in the app, on the devices least able to absorb it.
 *
 * The fix is the same one used for theme flashes: run the decision in a blocking
 * script in <head> and stamp the answer on <html>, so CSS can act on it before
 * anything is drawn.
 *
 * The predicate below is the ONLY copy. `useIsMobile` imports it, and the inline
 * script is generated from its own source via `toString()` — which is why it
 * takes `win` as an argument and closes over nothing: a function that referenced
 * an imported constant would serialize to a script that throws at runtime, and
 * minification would rename the reference out from under it.
 */

export type ShellMode = "mobile" | "desktop"

export function computeShellMode(win: Window): ShellMode {
  const MOBILE_BREAKPOINT = 768
  const MOBILE_USER_AGENT =
    /Android|webOS|iPhone|iPad|iPod|BlackBerry|BB10|IEMobile|Opera Mini|Mobile|Tablet/i
  const DESKTOP_PLATFORM = /Mac|Win|Linux x86|Linux i686|Linux armv|CrOS|X11/i

  function mediaMatches(query: string): boolean {
    return typeof win.matchMedia === "function" && win.matchMedia(query).matches
  }

  const nav = win.navigator as Navigator & {
    userAgentData?: { platform?: string; mobile?: boolean }
  }
  const platform = (nav.userAgentData && nav.userAgentData.platform) || nav.platform || ""
  const ua = nav.userAgent || ""

  // An iPad reporting itself as a Mac is still a tablet; a touchscreen Windows
  // laptop is still a desktop. Both matter, and neither is expressible in CSS —
  // which is why this runs in script rather than as a media query.
  const isDesktopPlatform =
    nav.userAgentData && nav.userAgentData.mobile === true
      ? false
      : /Mac/i.test(platform) && nav.maxTouchPoints > 1 && /Mobile|Safari/i.test(ua)
        ? false
        : DESKTOP_PLATFORM.test(platform) && !MOBILE_USER_AGENT.test(ua)

  if (isDesktopPlatform) return "desktop"

  const isNarrow = win.innerWidth < MOBILE_BREAKPOINT
  const hasCoarsePointer = mediaMatches("(pointer: coarse)") || nav.maxTouchPoints > 0
  const hasNoHover = mediaMatches("(hover: none)")
  const hasModernPointerSignals =
    typeof win.matchMedia === "function" &&
    (mediaMatches("(pointer: coarse)") ||
      mediaMatches("(pointer: fine)") ||
      mediaMatches("(hover: none)") ||
      mediaMatches("(hover: hover)"))
  const looksMobileByAgent = MOBILE_USER_AGENT.test(ua)

  const mobile =
    isNarrow && (hasModernPointerSignals ? hasCoarsePointer && hasNoHover : looksMobileByAgent)
  return mobile ? "mobile" : "desktop"
}

/** The attribute CSS keys off. Written before paint, kept current by the hook. */
export const SHELL_MODE_ATTRIBUTE = "data-shell"

export function applyShellMode(mode: ShellMode): void {
  if (typeof document === "undefined") return
  document.documentElement.setAttribute(SHELL_MODE_ATTRIBUTE, mode)
}

/**
 * The blocking script for <head>. Wrapped in try/catch because a shell that
 * cannot be decided must not take the page down with it — an unset attribute
 * simply means "assume desktop", which is what the app rendered before this
 * existed.
 */
export const SHELL_MODE_INLINE_SCRIPT = `(function(){try{var f=${computeShellMode.toString()};document.documentElement.setAttribute(${JSON.stringify(
  SHELL_MODE_ATTRIBUTE,
)},f(window))}catch(e){}})()`

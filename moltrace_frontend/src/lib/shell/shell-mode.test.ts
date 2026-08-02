import { describe, expect, it } from "vitest"
import { SHELL_MODE_INLINE_SCRIPT, computeShellMode } from "@/src/lib/shell/shell-mode"

function fakeWindow(o: {
  width: number; platform: string; ua: string; touch: number;
  coarse: boolean; noHover: boolean; hasMM?: boolean;
}) {
  const hasMM = o.hasMM !== false
  return {
    innerWidth: o.width,
    navigator: { platform: o.platform, userAgent: o.ua, maxTouchPoints: o.touch },
    matchMedia: hasMM
      ? (q: string) => ({
          matches:
            q === "(pointer: coarse)" ? o.coarse
            : q === "(pointer: fine)" ? !o.coarse
            : q === "(hover: none)" ? o.noHover
            : q === "(hover: hover)" ? !o.noHover
            : false,
        })
      : undefined,
  } as unknown as Window
}

const PHONE = { width: 390, platform: "iPhone", ua: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148", touch: 5, coarse: true, noHover: true }
const DESKTOP = { width: 1440, platform: "MacIntel", ua: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", touch: 0, coarse: false, noHover: false }
const NARROW_DESKTOP = { ...DESKTOP, width: 500 }
const TOUCH_LAPTOP = { width: 700, platform: "Win32", ua: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", touch: 10, coarse: true, noHover: true }

describe("shell mode", () => {
  it("calls a phone mobile", () => expect(computeShellMode(fakeWindow(PHONE))).toBe("mobile"))
  it("calls a desktop desktop", () => expect(computeShellMode(fakeWindow(DESKTOP))).toBe("desktop"))
  it("keeps a NARROW desktop window on the desktop shell", () =>
    expect(computeShellMode(fakeWindow(NARROW_DESKTOP))).toBe("desktop"))
  it("keeps a touchscreen Windows laptop on the desktop shell", () =>
    // The case a pure CSS pointer query would have got wrong.
    expect(computeShellMode(fakeWindow(TOUCH_LAPTOP))).toBe("desktop"))

  it("the inline script is valid JS and agrees with the function it was made from", () => {
    for (const cfg of [PHONE, DESKTOP, NARROW_DESKTOP, TOUCH_LAPTOP]) {
      const win = fakeWindow(cfg)
      let stamped = ""
      const doc = { documentElement: { setAttribute: (_k: string, v: string) => { stamped = v } } }
      // Run the real emitted script exactly as the browser would.
      new Function("window", "document", SHELL_MODE_INLINE_SCRIPT)(win, doc)
      expect(stamped).toBe(computeShellMode(win))
    }
  })
})

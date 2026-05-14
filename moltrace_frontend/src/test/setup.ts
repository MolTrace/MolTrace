import "@testing-library/jest-dom/vitest"

class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

globalThis.ResizeObserver =
  globalThis.ResizeObserver ?? (ResizeObserverStub as unknown as typeof ResizeObserver)

// uPlot reads window.devicePixelRatio via matchMedia at module init; jsdom
// has no matchMedia, which produced unhandled errors after the Plotly→uPlot
// swap. Provide a passive stub so the import is harmless in tests.
if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
      dispatchEvent() {
        return false
      },
    }),
  })
}

// jsdom doesn't ship Path2D — uPlot's series renderer constructs Path2D
// instances at draw time. A no-op constructor is enough for the test
// runtime; no actual painting is verified.
if (typeof globalThis.Path2D === "undefined") {
  class Path2DStub {
    addPath(): void {}
    closePath(): void {}
    moveTo(): void {}
    lineTo(): void {}
    bezierCurveTo(): void {}
    quadraticCurveTo(): void {}
    arc(): void {}
    arcTo(): void {}
    ellipse(): void {}
    rect(): void {}
    roundRect(): void {}
  }
  ;(globalThis as { Path2D: unknown }).Path2D = Path2DStub
}

// jsdom returns null from `canvas.getContext("2d")` because the optional
// `canvas` npm package isn't installed. uPlot's first paint then crashes
// with "Cannot read properties of null (reading 'clearRect')". Stubbing the
// 2D context with no-op methods keeps the mount path quiet — tests don't
// inspect pixel output, only that the component mounts.
if (
  typeof HTMLCanvasElement !== "undefined" &&
  typeof HTMLCanvasElement.prototype.getContext === "function"
) {
  const original = HTMLCanvasElement.prototype.getContext as (
    this: HTMLCanvasElement,
    contextId: string,
    ...args: unknown[]
  ) => unknown
  const ctxStub: Partial<CanvasRenderingContext2D> = {
    fillRect: () => undefined,
    clearRect: () => undefined,
    beginPath: () => undefined,
    moveTo: () => undefined,
    lineTo: () => undefined,
    closePath: () => undefined,
    stroke: () => undefined,
    fill: () => undefined,
    arc: () => undefined,
    rect: () => undefined,
    save: () => undefined,
    restore: () => undefined,
    translate: () => undefined,
    scale: () => undefined,
    rotate: () => undefined,
    setTransform: () => undefined,
    transform: () => undefined,
    drawImage: () => undefined,
    fillText: () => undefined,
    strokeText: () => undefined,
    measureText: () => ({ width: 0 }) as TextMetrics,
    getImageData: () =>
      ({ data: new Uint8ClampedArray(4), width: 1, height: 1 }) as ImageData,
    putImageData: () => undefined,
    createImageData: () =>
      ({ data: new Uint8ClampedArray(4), width: 1, height: 1 }) as ImageData,
    setLineDash: () => undefined,
    getLineDash: () => [],
    clip: () => undefined,
  }
  HTMLCanvasElement.prototype.getContext = function patched(
    contextId: string,
    ...args: unknown[]
  ) {
    const actual = original.call(this, contextId, ...args)
    if (actual) return actual
    if (contextId === "2d") return ctxStub as CanvasRenderingContext2D
    return null
  } as typeof HTMLCanvasElement.prototype.getContext
}

function createMemoryStorage(): Storage {
  const store = new Map<string, string>()

  return {
    get length() {
      return store.size
    },
    clear() {
      store.clear()
    },
    getItem(key: string) {
      return store.get(key) ?? null
    },
    key(index: number) {
      return Array.from(store.keys())[index] ?? null
    },
    removeItem(key: string) {
      store.delete(key)
    },
    setItem(key: string, value: string) {
      store.set(key, value)
    },
  }
}

if (typeof window !== "undefined" && typeof window.localStorage?.getItem !== "function") {
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: createMemoryStorage(),
  })
}

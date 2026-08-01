"use client"

import dynamic from "next/dynamic"

/**
 * The one lazy boundary for the drawing canvas.
 *
 * `ssr: false` is required, not stylistic: Ketcher reads `window` while its
 * module is evaluated, so rendering it on the server throws. Keeping the
 * `dynamic()` call in a single module means every surface that draws shares one
 * chunk and one Indigo worker, rather than each one minting its own.
 */
export const LazyStructureCanvas = dynamic(
  () => import("@/src/components/chemistry/StructureEditor").then((m) => m.StructureEditorCanvas),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[520px] items-center justify-center rounded-lg border border-dashed bg-muted/30">
        <p className="text-sm text-muted-foreground">Starting the drawing canvas…</p>
      </div>
    ),
  },
)

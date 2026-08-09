import { cn } from "@/lib/utils"

type MoleculeLogoMarkProps = {
  className?: string
}

/**
 * The MolTrace mark in site chrome — header, footer, sidebar, app shell.
 *
 * THIS IS THE DIMENSIONAL RENDER, AND THE FAVICON IS A DIFFERENT DRAWING. That is
 * deliberate, and it replaces the invariant this file used to carry ("change one
 * and you must change the other", pointing at the SVG duplicated into
 * scripts/generate-pwa-icons.mjs). Site chrome runs 20–40 CSS px, which is 40–120
 * PHYSICAL px on the screens nearly everyone has, and the render reads richly
 * there. A favicon is sized in DEVICE pixels — 16 means 16, with no retina
 * multiplier — and at that size the render has no legible letter while the drawn
 * mark stays crisp. Detailed mark where there is room, simplified where there is
 * not; neither is the old one.
 *
 * WHY THIS IS NOT THE SHARE CARD'S ASSET. That one removes the background by
 * deriving alpha from the render's own glow, which leaves the dark facets
 * TRANSPARENT. At 210px on the card's dark gradient that is invisible and
 * correct. At 32px the hexagon body simply is not there — only the bright "m" and
 * the rim are opaque — so the mark reads as a letter floating in a haze, and on
 * the light marketing header it collapses into a grey smudge.
 *
 * The fix is a hexagon silhouette that is CONSTRUCTED rather than detected,
 * because this render has none of its own to find: it is a lit object on a
 * surface with atmospheric spill, and every boundary in it is a gradient. The
 * generator fits a pointy-top hexagon to the art's measured height and verifies
 * the implied width against the measured one before masking. Four detection
 * approaches were tried first and all produced haze or a grey slab; they are
 * enumerated in scripts/generate-3d-mark-assets.mjs so nobody spends the
 * afternoon again.
 *
 * A rounded dark tile also works and was shipped briefly, but it puts a dark
 * square around the mark on a white header, which is the thing it was supposed to
 * fix. Both assets come from scripts/generate-3d-mark-assets.mjs.
 */
export function MoleculeLogoMark({ className }: MoleculeLogoMarkProps) {
  return (
    <div
      className={cn("relative flex items-center justify-center", className)}
      aria-hidden="true"
    >
      {/* A plain <img>, not next/image: a fixed-size 21KB asset in the header of
          every page, so the optimizer round-trip would cost more than it saves.
          Decorative — every call site sets "MolTrace" beside it, so an alt would
          make a screen reader say the name twice. */}
      <img
        src="/icons/moltrace-mark-3d-hex-128.png"
        alt=""
        width={128}
        height={128}
        className="h-full w-full object-contain"
      />
    </div>
  )
}

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
 * WHY A TILE AND NOT A CUT-OUT MARK. The share card uses the same render with its
 * background removed, and reusing that here was the obvious move. It fails, for a
 * reason only visible small: the alpha it derives from the render's own glow
 * leaves the dark facets TRANSPARENT. At 210px on the card's dark gradient that
 * is invisible and correct. At 32px the hexagon body simply is not there — only
 * the bright "m" and the rim are opaque — so the mark reads as a letter floating
 * in a haze, and on the light marketing header it collapses into a grey smudge.
 *
 * Rebuilding a solid body by masking the hexagon interior does not rescue it. The
 * render has no hard silhouette to mask to; its edge is a soft luminous falloff,
 * and masking a soft edge gives a soft edge. The tile sidesteps the whole problem:
 * a rounded dark square IS a hard silhouette, it is self-contained so it reads on
 * a light or a dark header without knowing which it is on, and the art inside is
 * exactly what was authored. It is what app icons have always done with luminous
 * artwork — and it is why these call sites were already asking for `rounded-xl`.
 *
 * Both assets come from scripts/generate-3d-mark-assets.mjs.
 */
export function MoleculeLogoMark({ className }: MoleculeLogoMarkProps) {
  return (
    <div
      className={cn("relative flex items-center justify-center", className)}
      aria-hidden="true"
    >
      {/* A plain <img>, not next/image: a fixed-size 27KB asset in the header of
          every page, so the optimizer round-trip would cost more than it saves.
          The corner radius is baked into the PNG rather than applied here,
          because call sites pass everything from `rounded-sm` to nothing at all
          and the tile should not change shape depending on where it appears.
          Decorative — every call site sets "MolTrace" beside it, so an alt would
          make a screen reader say the name twice. */}
      <img
        src="/icons/moltrace-mark-3d-tile-128.png"
        alt=""
        width={128}
        height={128}
        className="h-full w-full object-contain"
      />
    </div>
  )
}

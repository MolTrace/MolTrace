"use client"

import dynamic from "next/dynamic"
import { useEffect, useState } from "react"

const HeroMoleculeBackground = dynamic(
  () => import("./hero-molecule-background").then((m) => m.HeroMoleculeBackground),
  { ssr: false, loading: () => null },
)

function useAnimatedHeroEnabled() {
  const [enabled, setEnabled] = useState(false)

  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      setEnabled(false)
      return
    }

    const media = window.matchMedia("(min-width: 768px) and (prefers-reduced-motion: no-preference)")
    const sync = () => setEnabled(media.matches)

    sync()
    media.addEventListener("change", sync)
    return () => media.removeEventListener("change", sync)
  }, [])

  return enabled
}

/** WebGL ball-and-stick scene (transparent canvas over the grid plane). */
export function HeroMoleculeLayer() {
  const animated = useAnimatedHeroEnabled()

  if (animated) return <HeroMoleculeBackground />

  return (
    <div
      className="pointer-events-none absolute inset-0 z-[1] min-h-[520px] bg-[radial-gradient(circle_at_50%_18%,rgba(34,211,238,0.12),transparent_34%),radial-gradient(circle_at_18%_72%,rgba(52,211,153,0.1),transparent_30%),radial-gradient(circle_at_82%_64%,rgba(167,139,250,0.1),transparent_32%)]"
      aria-hidden
    />
  )
}

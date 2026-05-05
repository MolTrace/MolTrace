"use client"

import dynamic from "next/dynamic"

const HeroMoleculeBackground = dynamic(
  () => import("./hero-molecule-background").then((m) => m.HeroMoleculeBackground),
  { ssr: false, loading: () => null },
)

/** WebGL ball-and-stick scene (transparent canvas over the grid plane). */
export function HeroMoleculeLayer() {
  return <HeroMoleculeBackground />
}

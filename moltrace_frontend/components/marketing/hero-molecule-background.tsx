"use client"

import { Canvas, useFrame } from "@react-three/fiber"
import { Environment } from "@react-three/drei"
import * as THREE from "three"
import { Suspense, useMemo, useRef } from "react"

/** Stylistic palette — cyan / emerald / violet (reference artwork) */
const PALETTE = ["#22d3ee", "#34d399", "#a78bfa"] as const

const STICK_R = 0.032

type AtomNode = {
  position: THREE.Vector3
  color: string
  radius: number
}

function rng(seed: number) {
  const x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453
  return x - Math.floor(x)
}

class UnionFind {
  private p: number[]
  constructor(n: number) {
    this.p = Array.from({ length: n }, (_, i) => i)
  }
  find(i: number): number {
    if (this.p[i] !== i) this.p[i] = this.find(this.p[i])
    return this.p[i]
  }
  union(a: number, b: number) {
    const ra = this.find(a)
    const rb = this.find(b)
    if (ra !== rb) this.p[ra] = rb
  }
}

/** One dense hypothetical network: points in a spherical shell + distance bonds + bridge if needed */
function buildHypotheticalMolecule(atomCount = 104): { atoms: AtomNode[]; bonds: [number, number][] } {
  const atoms: AtomNode[] = []
  const golden = Math.PI * (3 - Math.sqrt(5))

  for (let i = 0; i < atomCount; i++) {
    const t = i / Math.max(1, atomCount - 1)
    const y = 1 - t * 2
    const rRing = Math.sqrt(Math.max(0, 1 - y * y))
    const theta = golden * i
    const radial = 2.35 + rng(i * 3.17) * 1.85
    const squash = 0.88 + rng(i * 9.2) * 0.24
    atoms.push({
      position: new THREE.Vector3(
        radial * rRing * Math.cos(theta) * squash,
        radial * y * (0.82 + 0.18 * rng(i * 4.1)),
        radial * rRing * Math.sin(theta) * squash,
      ),
      color: PALETTE[i % PALETTE.length],
      radius: 0.1 + rng(i * 6.31) * 0.048,
    })
  }

  const maxD = 1.14
  const bonds: [number, number][] = []
  for (let i = 0; i < atomCount; i++) {
    for (let j = i + 1; j < atomCount; j++) {
      if (atoms[i].position.distanceTo(atoms[j].position) < maxD) {
        bonds.push([i, j])
      }
    }
  }

  const uf = new UnionFind(atomCount)
  for (const [a, b] of bonds) {
    uf.union(a, b)
  }

  const roots = new Set<number>()
  for (let i = 0; i < atomCount; i++) {
    roots.add(uf.find(i))
  }

  const merged: [number, number][] = [...bonds]
  if (roots.size > 1) {
    const compMap = new Map<number, number[]>()
    for (let i = 0; i < atomCount; i++) {
      const r = uf.find(i)
      if (!compMap.has(r)) compMap.set(r, [])
      compMap.get(r)!.push(i)
    }
    const comps = [...compMap.values()]

    while (comps.length > 1) {
      let bestA = 0
      let bestB = 1
      let bestD = Infinity
      const c0 = comps[0]
      const c1 = comps[1]
      for (const i of c0) {
        for (const j of c1) {
          const d = atoms[i].position.distanceTo(atoms[j].position)
          if (d < bestD) {
            bestD = d
            bestA = i
            bestB = j
          }
        }
      }
      merged.push([Math.min(bestA, bestB), Math.max(bestA, bestB)])
      comps[0] = [...c0, ...c1]
      comps.splice(1, 1)
    }
  }

  return { atoms, bonds: merged }
}

function BondCylinder({
  from,
  to,
  rStart,
  rEnd,
}: {
  from: THREE.Vector3
  to: THREE.Vector3
  rStart: number
  rEnd: number
}) {
  const { position, quaternion, height } = useMemo(() => {
    const dir = new THREE.Vector3().subVectors(to, from)
    const len = dir.length()
    const n = dir.clone().divideScalar(len)
    const start = from.clone().add(n.clone().multiplyScalar(rStart))
    const end = to.clone().sub(n.clone().multiplyScalar(rEnd))
    const u = new THREE.Vector3().subVectors(end, start)
    const h = u.length()
    const mid = start.clone().add(end).multiplyScalar(0.5)
    const quat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), u.clone().normalize())
    return { position: mid, quaternion: quat, height: h }
  }, [from, to, rStart, rEnd])

  return (
    <mesh position={position} quaternion={quaternion} renderOrder={0}>
      <cylinderGeometry args={[STICK_R, STICK_R, height, 18]} />
      <meshPhysicalMaterial
        color="#c8cdd8"
        metalness={0.72}
        roughness={0.22}
        transparent
        opacity={0.72}
        envMapIntensity={1.1}
      />
    </mesh>
  )
}

function GlassAtom({ color, radius }: { color: string; radius: number }) {
  const emissive = useMemo(() => new THREE.Color(color).multiplyScalar(0.12), [color])
  return (
    <mesh renderOrder={1}>
      <sphereGeometry args={[radius, 40, 40]} />
      <meshPhysicalMaterial
        color={color}
        emissive={emissive}
        emissiveIntensity={0.85}
        metalness={0.08}
        roughness={0.14}
        transmission={0.62}
        thickness={0.55}
        ior={1.52}
        transparent
        opacity={0.78}
        clearcoat={0.9}
        clearcoatRoughness={0.12}
        envMapIntensity={1.15}
        attenuationColor={color}
        attenuationDistance={0.65}
      />
    </mesh>
  )
}

function HypotheticalMoleculeScene() {
  const root = useRef<THREE.Group>(null)

  const { atoms, bonds } = useMemo(() => buildHypotheticalMolecule(104), [])

  useFrame((_, delta) => {
    if (root.current) {
      root.current.rotation.y += delta * 0.055
      root.current.rotation.x = THREE.MathUtils.lerp(
        root.current.rotation.x,
        Math.sin(performance.now() * 0.00022) * 0.07,
        0.022,
      )
    }
  })

  return (
    <group ref={root}>
      {bonds.map(([i, j], k) => (
        <BondCylinder
          key={`b-${k}`}
          from={atoms[i].position}
          to={atoms[j].position}
          rStart={atoms[i].radius}
          rEnd={atoms[j].radius}
        />
      ))}
      {atoms.map((atom, i) => (
        <group key={`a-${i}`} position={atom.position}>
          <GlassAtom color={atom.color} radius={atom.radius} />
        </group>
      ))}
    </group>
  )
}

export function HeroMoleculeBackground() {
  return (
    <div className="pointer-events-none absolute inset-0 z-[1] min-h-[560px] w-full opacity-40">
      <Canvas
        camera={{ position: [0, 0.15, 10.2], fov: 34 }}
        gl={{
          alpha: true,
          antialias: true,
          powerPreference: "high-performance",
          stencil: false,
          depth: true,
        }}
        dpr={[1, 2]}
        style={{ width: "100%", height: "100%" }}
        onCreated={({ gl }) => {
          gl.setClearColor(0x000000, 0)
          gl.toneMapping = THREE.ACESFilmicToneMapping
          gl.toneMappingExposure = 1.08
        }}
      >
        <ambientLight intensity={0.38} />
        <directionalLight position={[10, 16, 8]} intensity={1.05} color="#ffffff" />
        <directionalLight position={[-12, -6, -8]} intensity={0.42} color="#93c5fd" />
        <pointLight position={[14, 4, 10]} intensity={0.55} color="#a5b4fc" />
        <pointLight position={[-8, 10, -6]} intensity={0.35} color="#6ee7b7" />
        <Suspense fallback={null}>
          <Environment preset="studio" environmentIntensity={0.5} />
        </Suspense>
        <HypotheticalMoleculeScene />
      </Canvas>
    </div>
  )
}

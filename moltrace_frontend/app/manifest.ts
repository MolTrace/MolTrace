import type { MetadataRoute } from "next"

const PWA_ASSET_VERSION = "2026-05-08-v1"

function versionedIcon(src: string) {
  return `${src}?v=${PWA_ASSET_VERSION}`
}

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "MolTrace",
    short_name: "MolTrace",
    description: "AI-native spectroscopy, regulatory intelligence and reaction optimization.",
    start_url: "/",
    display: "standalone",
    background_color: "#070b12",
    theme_color: "#070b12",
    icons: [
      {
        src: versionedIcon("/icons/moltrace-mark.svg"),
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any",
      },
      {
        src: versionedIcon("/icons/icon-192.png"),
        sizes: "192x192",
        type: "image/png",
      },
      {
        src: versionedIcon("/icons/icon-512.png"),
        sizes: "512x512",
        type: "image/png",
      },
      {
        src: versionedIcon("/icons/maskable-icon-512.png"),
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  }
}

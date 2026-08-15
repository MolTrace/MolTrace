/**
 * The single source of truth for icon artwork versioning.
 *
 * Icons are served `public, max-age=31536000, immutable` (next.config.mjs), so a
 * URL is frozen in browser caches for a year — the `?v=` query is the ONLY way
 * to publish new artwork. Every reference to a file under /icons must therefore
 * go through {@link versionedIcon}; a bare `/icons/...` string is a bug that
 * cannot be fixed by redeploying.
 *
 * Publishing new artwork = regenerate the assets AND bump this constant in the
 * same change. `public/sw.js` cannot import from here (it is plain JS served as
 * a static file), so it carries a literal copy that
 * `sw-asset-version.test.ts` pins to this value.
 */
export const PWA_ASSET_VERSION = "2026-08-09-neon-prism-raised-m-v1"

export function versionedIcon(src: string): string {
  return `${src}?v=${PWA_ASSET_VERSION}`
}

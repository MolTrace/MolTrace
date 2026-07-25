/**
 * IndexNow submitter — pings the IndexNow API with the site's canonical URLs so
 * participating engines (Bing, Yandex, Seznam, Naver — and, downstream, AI
 * search surfaces like ChatGPT Search / Copilot) re-crawl promptly.
 *
 *   ⚠️  Google does NOT consume IndexNow. This does nothing for Google indexing;
 *       Google discovery is driven by Search Console + the sitemap. Use this for
 *       Bing / AI-search reach only.
 *
 * Ownership is proven by a key file served at the site root:
 *     public/<key>.txt   (contains exactly <key>)
 * which resolves to https://moltrace.co/<key>.txt — the `keyLocation` below.
 *
 * The URL list is read from the LIVE sitemap.xml, so it is always in sync with
 * app/sitemap.ts (single source of truth — no drift, no hardcoded route list).
 *
 * Metered + human-gated by design: it DRY-RUNS by default (prints the payload,
 * sends nothing). Pass --submit to actually POST.
 *
 *   node scripts/indexnow-submit.mjs                     # dry run against prod
 *   node scripts/indexnow-submit.mjs --submit            # really submit
 *   node scripts/indexnow-submit.mjs --sitemap http://localhost:3000/sitemap.xml
 *
 * Env: INDEXNOW_KEY (defaults to the committed key), SITE_URL (defaults to the
 * apex). Run AFTER a production deploy — engines fetch each URL to confirm it.
 */

const KEY = process.env.INDEXNOW_KEY || "cb7050ed022a54082fb0ae1b5285c34d"
const SITE_URL = (process.env.SITE_URL || "https://moltrace.co").replace(/\/+$/, "")
const INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"

const args = process.argv.slice(2)
const submit = args.includes("--submit")
const sitemapArg = args[args.indexOf("--sitemap") + 1]
const SITEMAP_URL =
  args.includes("--sitemap") && sitemapArg ? sitemapArg : `${SITE_URL}/sitemap.xml`

/** Extract <loc> URLs from a sitemap XML string. */
function parseSitemap(xml) {
  return [...xml.matchAll(/<loc>\s*([^<\s]+)\s*<\/loc>/g)].map((m) => m[1])
}

async function main() {
  console.log(`IndexNow submit — reading ${SITEMAP_URL}`)
  const res = await fetch(SITEMAP_URL, { headers: { "user-agent": "moltrace-indexnow" } })
  if (!res.ok) {
    console.error(`✗ Could not fetch sitemap: HTTP ${res.status}`)
    process.exit(1)
  }
  const urlList = parseSitemap(await res.text())
  if (urlList.length === 0) {
    console.error("✗ No <loc> URLs found in sitemap — nothing to submit.")
    process.exit(1)
  }

  // IndexNow requires every submitted URL to share the host of keyLocation.
  const host = new URL(SITE_URL).host
  const offHost = urlList.filter((u) => new URL(u).host !== host)
  if (offHost.length) {
    console.error(`✗ ${offHost.length} sitemap URL(s) are not on ${host}; refusing to submit:`)
    offHost.forEach((u) => console.error(`    ${u}`))
    process.exit(1)
  }

  const body = {
    host,
    key: KEY,
    keyLocation: `${SITE_URL}/${KEY}.txt`,
    urlList,
  }

  console.log(`  host:        ${body.host}`)
  console.log(`  keyLocation: ${body.keyLocation}`)
  console.log(`  urls:        ${urlList.length}`)
  urlList.forEach((u) => console.log(`    • ${u}`))

  if (!submit) {
    console.log("\nDRY RUN — nothing submitted. Re-run with --submit to POST to IndexNow.")
    return
  }

  const resp = await fetch(INDEXNOW_ENDPOINT, {
    method: "POST",
    headers: { "content-type": "application/json; charset=utf-8" },
    body: JSON.stringify(body),
  })
  // IndexNow returns 200 or 202 on success; 4xx on key/host problems.
  const text = await resp.text().catch(() => "")
  if (resp.ok) {
    console.log(`\n✓ Submitted ${urlList.length} URLs — HTTP ${resp.status} ${text || "OK"}`)
  } else {
    console.error(`\n✗ IndexNow rejected the submission — HTTP ${resp.status} ${text}`)
    process.exit(1)
  }
}

main().catch((err) => {
  console.error("✗ Unexpected error:", err?.message || err)
  process.exit(1)
})

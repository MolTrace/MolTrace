import { NextRequest, NextResponse } from "next/server"

// Browser -> Vercel -> backend proxy. Every authed/app request goes through
// here as a same-origin call to `/api/backend/*`, which this catch-all forwards
// to the FastAPI backend. It MUST deploy as a dynamic Node serverless function
// (hence `force-dynamic`); if it is ever served as a static/missing route the
// client only sees a 404 HTML page and surfaces a generic "Request could not be
// completed" error.
//
// DEPLOY NOTE: this is a bracketed catch-all (`[...path]`). After renaming or
// moving this folder, redeploy on Vercel with the build cache CLEARED
// ("Redeploy" -> uncheck "Use existing Build Cache", or `vercel --prod
// --force`). Vercel reuses `.next/cache` across deploys keyed on file content,
// so a folder move can leave a stale/missing function output that normal pushes
// will not refresh until this file's content changes.
/**
 * Mirrors `error_codes.PUBLIC_CODES` in the backend — the codes deemed safe to
 * survive 401/403 sanitization. Anything not listed here is stripped, so adding a
 * public code on the backend without adding it here fails CLOSED (the client sees
 * a generic denial) rather than leaking.
 */
const PUBLIC_ERROR_CODES: ReadonlySet<string> = new Set([
  "module_not_licensed",
  "step_up_required",
  "token_expired",
  "token_invalid",
  "token_reuse_detected",
  "product_not_in_plan",
  "product_not_enabled",
  "product_not_provisioned",
  "role_required",
])

export const dynamic = "force-dynamic"

type RouteContext = {
  params: Promise<{ path?: string[] }>
}

const hopByHopHeaders = new Set([
  "connection",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
])

function authFailureMessage(status: number) {
  if (status === 403) return "You do not have access to perform this action."
  return "Sign in to access live MolTrace data."
}

function backendBaseUrl() {
  // Explicit 127.0.0.1 avoids a macOS+Node20+ DNS hang where fetch() resolves
  // "localhost" to ::1, the backend listens on IPv4 only, and the request
  // stalls until the browser fires ERR_TIMED_OUT. Apply the same normalization
  // when API_BASE_URL is set to a localhost variant via .env.local.
  const raw =
    process.env.API_BASE_URL ||
    (process.env.NODE_ENV === "production"
      ? // Production backend on GCP Cloud Run (moltrace-prod project). API_BASE_URL,
        // set in the Vercel dashboard, always wins — this is only the fallback.
        "https://moltrace-backend-304031104668.us-central1.run.app"
      : "http://127.0.0.1:8000")
  return raw.replace(/^http:\/\/localhost(:|\/|$)/i, "http://127.0.0.1$1")
}

async function proxy(request: NextRequest, context: RouteContext) {
  const { path = [] } = await context.params
  const target = new URL(`${backendBaseUrl().replace(/\/$/, "")}/${path.map(encodeURIComponent).join("/")}`)
  target.search = request.nextUrl.search

  const headers = new Headers(request.headers)
  for (const key of Array.from(headers.keys())) {
    if (hopByHopHeaders.has(key.toLowerCase())) {
      headers.delete(key)
    }
  }

  const method = request.method.toUpperCase()
  const hasBody = method !== "GET" && method !== "HEAD"

  // SSO is the one flow where the backend answers with a 302 that the *browser*
  // must follow (the IdP authorize hop on `/auth/sso/{slug}/login`). For those
  // paths, forward the redirect verbatim instead of letting fetch chase it
  // server-side (the default) — which would fetch the IdP page on the server and
  // return its HTML, breaking the login. Every other path keeps follow semantics.
  const forwardRedirect = path[0] === "auth" && path[1] === "sso"

  let response: Response
  try {
    response = await fetch(target, {
      method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      redirect: forwardRedirect ? "manual" : "follow",
    })
  } catch (err) {
    console.error("[api/backend proxy] fetch failed:", target.toString(), err)
    return NextResponse.json(
      {
        // `detail` is surfaced verbatim in the UI — keep it plain language, no "backend".
        detail: "Could not reach the MolTrace service. Please retry in a moment.",
        target: target.toString(),
        error: String((err as Error)?.message ?? err),
      },
      { status: 503 }
    )
  }

  const responseHeaders = new Headers(response.headers)
  responseHeaders.delete("content-encoding")
  responseHeaders.delete("content-length")

  if (response.status === 401 || response.status === 403) {
    responseHeaders.set("content-type", "application/json")
    // Preserve the machine-readable `code` for errors the backend marks public,
    // and sanitize everything else so internal auth detail cannot leak.
    //
    // THIS USED TO MATCH ON `detail`. It regex-tested the body for four literal
    // detail strings, which was wrong twice over. `detail` is prose written for a
    // human and changes whenever someone improves the wording — matching it makes
    // a copy edit a breaking API change. And it only ran for 401, so a 403
    // carrying `module_not_licensed` or any of the four upgrade states had its
    // body replaced and arrived at the client indistinguishable from a plain
    // "access denied".
    //
    // The list below mirrors error_codes.PUBLIC_CODES on the backend. It is still
    // a second copy — the proxy cannot import Python — but a copy of stable
    // identifiers rather than of prose, and one that fails safe: an unknown code
    // is sanitized, never passed through.
    const raw = await response.text()
    let publicCode: string | null = null
    try {
      const body: unknown = JSON.parse(raw)
      if (body && typeof body === "object") {
        const code = (body as { code?: unknown }).code
        if (typeof code === "string" && PUBLIC_ERROR_CODES.has(code)) publicCode = code
      }
    } catch {
      // Not JSON, or malformed. Fall through to the sanitized body.
    }

    if (publicCode) {
      // Pass the code through, but still replace `detail` with our own copy: the
      // client should branch on the code, and the backend's prose is not written
      // for this surface.
      return new Response(
        JSON.stringify({ code: publicCode, detail: authFailureMessage(response.status) }),
        { status: response.status, statusText: response.statusText, headers: responseHeaders },
      )
    }
    return new Response(JSON.stringify({ detail: authFailureMessage(response.status) }), {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    })
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders,
  })
}

export function OPTIONS() {
  return new NextResponse(null, {
    status: 204,
    headers: {
      "access-control-allow-methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
      "access-control-allow-headers": "authorization,content-type,x-request-id",
      "access-control-max-age": "86400",
    },
  })
}

export const GET = proxy
export const HEAD = proxy
export const POST = proxy
export const PUT = proxy
export const PATCH = proxy
export const DELETE = proxy

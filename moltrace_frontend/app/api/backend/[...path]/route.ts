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
      ? "https://moltrace-backend.onrender.com"
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

  let response: Response
  try {
    response = await fetch(target, {
      method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
    })
  } catch (err) {
    console.error("[api/backend proxy] fetch failed:", target.toString(), err)
    return NextResponse.json(
      {
        detail: "Backend connection failed. Please retry in a moment.",
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

import { NextRequest, NextResponse } from "next/server"

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
  return "Sign in to continue. If you already signed in, your session may have expired."
}

function backendBaseUrl() {
  return (
    process.env.API_BASE_URL ||
    (process.env.NODE_ENV === "production"
      ? "https://moltrace-backend.onrender.com"
      : "http://localhost:8000")
  )
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

  const response = await fetch(target, {
    method,
    headers,
    body: hasBody ? await request.arrayBuffer() : undefined,
    cache: "no-store",
  })

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
export const POST = proxy
export const PUT = proxy
export const PATCH = proxy
export const DELETE = proxy

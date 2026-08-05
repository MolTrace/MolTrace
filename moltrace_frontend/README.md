# MolTrace Frontend

Next.js 16 / React 19 App Router app serving both the public marketing site and the signed-in
product. Node 22.14.0 and pnpm 11.0.3 (pinned in `package.json` `engines`).

## Run

Two processes: the backend on `:8000` and this app on `:3000`.

Backend, from `moltrace_backend/`:

```bash
uv sync --frozen --extra fid --extra dev
uv run python -m uvicorn nmrcheck.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend, from `moltrace_frontend/`:

```bash
pnpm install
pnpm dev
```

Verify the backend directly, then through the proxy:

```bash
curl http://localhost:8000/openapi.json
curl http://localhost:3000/api/backend/openapi.json
```

## Environment

No `.env.local` is needed for the default local setup — the proxy already targets
`http://127.0.0.1:8000` in development. Create one only to point at a different backend:

```bash
# moltrace_frontend/.env.local
API_BASE_URL=http://127.0.0.1:8001
```

| Variable | Purpose |
|---|---|
| `API_BASE_URL` | Server-side proxy target. Defaults to `http://127.0.0.1:8000` in development and the Cloud Run URL in production. A `localhost` value is rewritten to `127.0.0.1` — on macOS with Node 20+, `fetch()` resolves `localhost` to `::1` while the backend listens on IPv4 only, and the request hangs until the browser times out. |
| `NEXT_PUBLIC_API_BASE_URL` | Public API base, default `/api/backend`. An absolute `http(s)://` value is **deliberately ignored** by `lib/api/client.ts` — browser code must always call the same-origin proxy, never the backend directly. |

If you expose the dev server on a LAN address, remote browsers still call
`http://<host>:3000/api/backend/...`. That is the point of the proxy: it keeps the API same-origin,
so no CORS config, no mixed-content block, and no backend URL baked into the bundle.

## Scripts

```bash
pnpm dev
pnpm build         # NOTE: next.config.mjs sets typescript.ignoreBuildErrors — this does NOT typecheck
pnpm start
pnpm typecheck     # tsc --noEmit — the real type gate
pnpm lint          # eslint .
pnpm test          # vitest (watch mode); CI runs `pnpm test -- --run`
pnpm test:watch
pnpm vitest path/to/file.test.tsx --run   # single file
```

## Generate OpenAPI types

`src/lib/api/schema.d.ts` is the binding FE↔BE contract. Regenerate it whenever backend routes or
models change — **the backend must be running on `:8000` first**:

```bash
pnpm generate:openapi
# openapi-typescript http://localhost:8000/openapi.json -o src/lib/api/schema.d.ts
```

## Layout

- **`app/`** at the project root is the active App Router tree. `src/app/` is a non-routed mirror
  kept for a possible future migration — Next.js resolves `app/` at the root when it exists, so
  nothing under `src/app/` renders, and it has already drifted from its root counterparts. Edit
  `app/`.
- Both `components/` + `lib/` (root) and `src/components/` + `src/lib/` are live and imported. The
  `@/*` alias maps to `./*`, so `@/components/…` resolves to the root tree and `@/src/lib/…` to the
  src tree. Check which one a neighbouring file uses before adding a sibling.
- `app/api/backend/[...path]/route.ts` is the same-origin proxy. It **sanitizes 401/403 response
  bodies** so internal auth details never reach the browser, with one deliberate allowlist: a 401
  whose `detail` is exactly `step_up_required`, `token_expired`, `token_invalid`, or
  `token_reuse_detected` passes through verbatim, because the step-up and rotating-refresh flows
  must act on it. Any other `detail` on a 401/403 is replaced — branch on the status code, not the
  message.

Useful routes while developing: `/` (marketing), `/platform`, `/spectracheck`, `/regulatory-hub`,
`/reaction-optimization`, `/dashboard`, `/api-test`.

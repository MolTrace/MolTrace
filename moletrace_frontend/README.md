# MolTrace Frontend

## Environment

Create `.env.local`:

```bash
NEXT_PUBLIC_API_BASE_URL=/api/backend
API_BASE_URL=http://localhost:8000
```

Browser code calls `/api/backend/*`. The Next.js server forwards those requests to `API_BASE_URL`.

## Run Backend

From `week10/`:

```bash
PYTHONPATH=src uv run uvicorn nmrcheck.web:app --reload --host 0.0.0.0 --port 8000
```

Test directly:

```bash
curl http://localhost:8000/openapi.json
```

## Run Frontend

From `week10/moletrace_frontend/`:

```bash
pnpm install
pnpm dev --hostname 0.0.0.0 --port 3000
```

## Generate OpenAPI Types

Requires the backend to be running at `http://localhost:8000`:

```bash
pnpm generate:openapi
```

## Test Proxy

```bash
curl http://localhost:3000/api/backend/openapi.json
```

UI routes:

- `http://localhost:3000/api-test`
- `http://localhost:3000/dashboard`
- `http://localhost:3000/platform`
- `http://localhost:3000/spectracheck`

If this frontend is exposed at `http://35.16.103.225:3000`, remote browsers still call `http://35.16.103.225:3000/api/backend/...`; do not make browser code call `localhost:8000` directly.

# Frontend Backend Integration Checklist

Do not polish or expand the UI until one backend-connected vertical slice works.

1. Start backend:

```bash
PYTHONPATH=src uv run uvicorn nmrcheck.web:app --reload --host 0.0.0.0 --port 8000
```

2. Start frontend:

```bash
pnpm dev --hostname 0.0.0.0 --port 3000
```

3. Test backend:

```bash
curl http://localhost:8000/openapi.json
```

4. Test frontend proxy:

```bash
curl http://localhost:3000/api/backend/openapi.json
```

5. Generate OpenAPI:

```bash
pnpm generate:openapi
```

OpenAPI generation requires the backend OpenAPI schema endpoint to be available at:

```text
http://localhost:8000/openapi.json
```

If the backend is not running, `pnpm generate:openapi` fails, but frontend development can still continue. Start the backend and re-run generation when ready.

6. Confirm `.env.local`:

```bash
NEXT_PUBLIC_API_BASE_URL=/api/backend
API_BASE_URL=http://localhost:8000
```

7. Test API test page:

http://localhost:3000/api-test

8. Test dashboard:

http://localhost:3000/dashboard

9. Test SpectraCheck:

http://localhost:3000/spectracheck

10. Run SpectraCheck Analysis.

11. Confirm backend result appears.

# Week 20 Deployment Hardening Checklist

## Render/Railway Environment Variables

Required:
- `APP_ENV=production`
- `DEBUG=false`
- `DATABASE_URL=<managed database URL>`
- `BASE_URL=<your public app URL>`
- `HEALTHCHECK_PATH=/health`
- `ADMIN_EMAILS=<admin email list>`
- `API_KEY=<long random value>`

Recommended:
- `ALLOWED_ORIGINS=<your public app URL>`
- `REDIS_URL=<managed Redis URL>`
- `QUEUE_NAME=nmrcheck`

## Health And Diagnostics

- Public health check: `GET /health`
- Admin diagnostics: `GET /admin/deployment`

The diagnostics endpoint reports startup issues, Redis configuration, optional FID dependency readiness, and configured beta vendors.

## Raw FID Dependencies

Raw Bruker and Varian/Agilent processing requires the optional FID dependency group:

```bash
uv sync --extra fid
```

Render deploys should install with `uv sync --frozen --no-dev --extra fid`.

## Regression Testing

Run:

```bash
PYTHONPATH=src uv run pytest
```

For local SQLite schema changes during active development, reset the local DB only when you deliberately want a fresh test database.

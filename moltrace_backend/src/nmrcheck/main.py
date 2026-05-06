from __future__ import annotations

import logging

import uvicorn
from fastapi.responses import HTMLResponse

from .api import create_app
from .settings import get_settings

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
app = create_app(settings=settings)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root() -> str:
    return """
    <!doctype html>
    <html lang='en'>
      <head>
        <meta charset='utf-8' />
        <meta name='viewport' content='width=device-width, initial-scale=1' />
        <title>MolTrace API</title>
        <style>body{font-family:Arial,sans-serif;max-width:840px;margin:2rem auto;padding:0 1rem;}code{background:#f5f5f5;padding:0.2rem 0.4rem;}a{display:block;margin:0.5rem 0;}</style>
      </head>
      <body>
        <h1>MolTrace API</h1>
        <p>The service is running.</p>
        <a href='/docs'>OpenAPI docs</a>
        <a href='/health'>Health check</a>
        <a href='/queue/status'>Queue status</a>
      </body>
    </html>
    """



def run() -> None:
    uvicorn.run(
        "nmrcheck.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.app_env == "development" and settings.debug,
    )

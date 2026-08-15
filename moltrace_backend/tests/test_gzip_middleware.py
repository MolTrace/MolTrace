"""Large JSON responses must go out compressed (Prompt 2, A4).

Measured raw-FID preview bodies are 377-650 KB of float JSON and gzip 5-8x;
before this middleware existed every byte crossed the wire uncompressed. Small
bodies stay uncompressed (minimum_size), so tiny health checks pay nothing.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_large_json_response_is_gzipped(client: TestClient) -> None:
    response = client.get("/openapi.json", headers={"accept-encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"


def test_small_response_is_not_gzipped(client: TestClient) -> None:
    response = client.get("/health", headers={"accept-encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers.get("content-encoding") is None

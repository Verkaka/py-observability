"""
FastAPI / Starlette middleware.

Automatically records:
  - http_requests_total
  - http_request_duration_seconds
  - http_requests_in_flight

Route pattern (e.g. /users/{id}) is used as the label, not the raw URL,
to keep cardinality low.

Usage:
    from sre_observability.middleware.fastapi import PrometheusMiddleware
    app.add_middleware(PrometheusMiddleware, config=cfg)
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match

from sre_observability.metrics.http import HttpMetrics

if TYPE_CHECKING:
    from sre_observability.config import ObservabilityConfig


class PrometheusMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: "ObservabilityConfig") -> None:
        super().__init__(app)
        self._metrics = HttpMetrics(config)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        route = _resolve_route(request)
        method = request.method
        inflight = self._metrics.track_inflight(method, route)
        inflight.inc()
        start = time.perf_counter()
        status_code = 500
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start
            inflight.dec()
            self._metrics.record_request(method, route, status_code, duration)


def _resolve_route(request: Request) -> str:
    """Return the matched route template, or the raw path as fallback."""
    if request.app and hasattr(request.app, "routes"):
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                return getattr(route, "path", request.url.path)
    return request.url.path


# ------------------------------------------------------------------
# Optional: OTel auto-instrumentation helper
# ------------------------------------------------------------------
def instrument_fastapi(app, config: "ObservabilityConfig") -> None:
    """
    Attach both Prometheus middleware and OTel FastAPI instrumentation.

    Call this after creating the FastAPI app:
        instrument_fastapi(app, cfg)
    """
    app.add_middleware(PrometheusMiddleware, config=config)
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        pass

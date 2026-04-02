"""
Flask middleware (before/after_request hooks).

Usage:
    from sre_observability.middleware.flask import instrument_flask
    instrument_flask(app, cfg)
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sre_observability.config import ObservabilityConfig

from sre_observability.metrics.http import HttpMetrics

_INFLIGHT_KEY = "_sre_obs_inflight"
_START_KEY = "_sre_obs_start"


def instrument_flask(app, config: "ObservabilityConfig") -> None:
    """Register before/after_request hooks on a Flask app."""
    metrics = HttpMetrics(config)

    @app.before_request
    def _before():
        from flask import g, request

        route = _resolve_flask_route(request)
        inflight = metrics.track_inflight(request.method, route)
        inflight.inc()
        g._sre_obs_inflight = inflight
        g._sre_obs_start = time.perf_counter()
        g._sre_obs_route = route

    @app.after_request
    def _after(response):
        from flask import g, request

        inflight = getattr(g, "_sre_obs_inflight", None)
        if inflight is not None:
            inflight.dec()
        start = getattr(g, "_sre_obs_start", None)
        route = getattr(g, "_sre_obs_route", request.path)
        if start is not None:
            metrics.record_request(
                request.method,
                route,
                response.status_code,
                time.perf_counter() - start,
            )
        return response

    # OTel auto-instrumentation
    try:
        from opentelemetry.instrumentation.flask import FlaskInstrumentor

        FlaskInstrumentor().instrument_app(app)
    except ImportError:
        pass


def _resolve_flask_route(request) -> str:
    """Return the URL rule template (e.g. /users/<int:id>), or raw path."""
    rule = request.url_rule
    if rule:
        return rule.rule
    return request.path

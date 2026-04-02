"""
HTTP metrics: request count, latency histogram, in-flight gauge.

Shared metric definitions used by both FastAPI and Flask middleware,
so Prometheus only registers each metric once regardless of which
framework is in use.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import prometheus_client as prom

if TYPE_CHECKING:
    from sre_observability.config import ObservabilityConfig

# label cardinality: keep route-level, not full URL (avoid high cardinality)
_HTTP_LABEL_NAMES = ["application", "namespace", "environment", "version", "method", "route", "status_code"]
_INFLIGHT_LABEL_NAMES = ["application", "namespace", "environment", "version", "method", "route"]

# Buckets covering fast microservices up to slow batch endpoints (seconds)
_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class HttpMetrics:
    """
    Prometheus metrics for HTTP request tracking.

    A single instance is shared across all middleware so that
    Prometheus does not get duplicate registrations.
    """

    _instance: "HttpMetrics | None" = None

    def __new__(cls, config: "ObservabilityConfig") -> "HttpMetrics":
        # Singleton per process – metrics can only be registered once
        if cls._instance is None:
            obj = super().__new__(cls)
            obj._initialized = False
            cls._instance = obj
        return cls._instance

    def __init__(self, config: "ObservabilityConfig") -> None:
        if self._initialized:  # type: ignore[has-type]
            return
        self._config = config
        self._base_labels = config.base_labels()

        self.requests_total = prom.Counter(
            "http_requests_total",
            "Total number of HTTP requests",
            labelnames=_HTTP_LABEL_NAMES,
            registry=prom.REGISTRY,
        )
        self.request_duration_seconds = prom.Histogram(
            "http_request_duration_seconds",
            "HTTP request latency in seconds",
            labelnames=_HTTP_LABEL_NAMES,
            buckets=_LATENCY_BUCKETS,
            registry=prom.REGISTRY,
        )
        self.requests_in_flight = prom.Gauge(
            "http_requests_in_flight",
            "Number of HTTP requests currently being processed",
            labelnames=_INFLIGHT_LABEL_NAMES,
            registry=prom.REGISTRY,
        )
        self._initialized = True

    def _labels(self, method: str, route: str, status_code: int | str) -> dict:
        return {
            **self._base_labels,
            "method": method.upper(),
            "route": route,
            "status_code": str(status_code),
        }

    def _inflight_labels(self, method: str, route: str) -> dict:
        return {
            **self._base_labels,
            "method": method.upper(),
            "route": route,
        }

    def record_request(
        self,
        method: str,
        route: str,
        status_code: int | str,
        duration: float,
    ) -> None:
        lbls = self._labels(method, route, status_code)
        self.requests_total.labels(**lbls).inc()
        self.request_duration_seconds.labels(**lbls).observe(duration)

    def track_inflight(self, method: str, route: str) -> prom.Gauge:
        """Return the in-flight gauge label set (use as context manager)."""
        return self.requests_in_flight.labels(**self._inflight_labels(method, route))

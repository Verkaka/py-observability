"""
Core initialization: one-stop setup for Prometheus + OpenTelemetry.

Usage:
    from sre_observability import ObservabilityConfig, setup_observability

    cfg = ObservabilityConfig(namespace="team")
    obs = setup_observability(cfg)  # auto-detects container vs VM
"""
from __future__ import annotations

import atexit
import logging
from typing import TYPE_CHECKING

from prometheus_client import start_http_server

from sre_observability.metrics.runtime import RuntimeMetricsCollector
from sre_observability.tracing.setup import setup_tracing

if TYPE_CHECKING:
    from sre_observability.config import ObservabilityConfig

logger = logging.getLogger(__name__)


class ObservabilityManager:
    """Manages lifecycle of metrics collectors and tracing."""

    def __init__(
        self,
        config: "ObservabilityConfig",
        start_metrics_server: bool | None = None,
    ) -> None:
        self.config = config
        self.config.validate()

        # Runtime metrics (CPU, memory, GC, etc.)
        self.runtime_collector = RuntimeMetricsCollector(config, interval=15.0)
        self.runtime_collector.start()

        # OpenTelemetry tracing
        self.tracer_provider = setup_tracing(config)

        # Auto-detect or explicit metrics mode
        use_pushgateway = config.should_use_pushgateway()

        # Explicit start_metrics_server overrides auto-detection
        if start_metrics_server is None:
            # Auto mode: Pushgateway for VM, HTTP server for container
            use_http_server = not use_pushgateway
        else:
            use_http_server = start_metrics_server

        # Pushgateway mode
        self.pushgateway = None
        if use_pushgateway:
            from sre_observability.metrics.pushgateway import PushgatewayCollector
            self.pushgateway = PushgatewayCollector(config)
            self.pushgateway.start()
            logger.info(
                "Pushgateway mode enabled (url=%s, interval=%ds)",
                config.pushgateway_url or "auto-detected",
                config.pushgateway_interval,
            )

        # Standalone Prometheus HTTP server
        self._metrics_server_started = False
        if use_http_server:
            start_http_server(config.metrics_port, addr="0.0.0.0")
            self._metrics_server_started = True
            logger.info(
                "Prometheus metrics server started on :%d%s",
                config.metrics_port,
                config.metrics_path,
            )

        atexit.register(self.shutdown)

    def shutdown(self) -> None:
        """Stop background collectors and flush traces."""
        self.runtime_collector.stop()
        if self.pushgateway:
            self.pushgateway.stop()
        if hasattr(self.tracer_provider, "shutdown"):
            self.tracer_provider.shutdown()
        logger.info("Observability shutdown complete")


def setup_observability(
    config: "ObservabilityConfig",
    start_metrics_server: bool | None = None,
) -> ObservabilityManager:
    """
    Initialize all observability components.

    Args:
        config: Service identity and environment config
        start_metrics_server: Explicitly enable/disable standalone HTTP server.
            If None (default), auto-detects:
            - Container (K8s/Docker) → HTTP server on :9090
            - VM → Pushgateway mode (requires pushgateway_url or PROM_PUSHGATEWAY_URL)

    Returns:
        ObservabilityManager instance (call .shutdown() on exit if needed)
    """
    return ObservabilityManager(config, start_metrics_server)

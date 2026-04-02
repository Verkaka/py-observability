"""
Core initialization: one-stop setup for Prometheus + OpenTelemetry.

Usage:
    from sre_observability import ObservabilityConfig, setup_observability

    cfg = ObservabilityConfig(application="my-service", namespace="team")
    obs = setup_observability(cfg, start_metrics_server=True)
    # ... at shutdown:
    obs.shutdown()
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
        start_metrics_server: bool = False,
    ) -> None:
        self.config = config
        self.config.validate()

        # Runtime metrics (CPU, memory, GC, etc.)
        self.runtime_collector = RuntimeMetricsCollector(config, interval=15.0)
        self.runtime_collector.start()

        # OpenTelemetry tracing
        self.tracer_provider = setup_tracing(config)

        # Pushgateway mode (for VM deployments)
        self.pushgateway = None
        if config.pushgateway_url:
            from sre_observability.metrics.pushgateway import PushgatewayCollector
            self.pushgateway = PushgatewayCollector(config)
            self.pushgateway.start()
            logger.info("Pushgateway mode enabled: %s", config.pushgateway_url)

        # Optional: standalone Prometheus HTTP server
        self._metrics_server_started = False
        if start_metrics_server:
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
    start_metrics_server: bool = False,
) -> ObservabilityManager:
    """
    Initialize all observability components.

    Args:
        config: Service identity and environment config
        start_metrics_server: If True, start a standalone HTTP server on
            config.metrics_port (default 9090) to serve /metrics.
            Use this for Flask or when you don't want to expose /metrics
            on the main application port.

    Returns:
        ObservabilityManager instance (call .shutdown() on exit if needed)
    """
    return ObservabilityManager(config, start_metrics_server)

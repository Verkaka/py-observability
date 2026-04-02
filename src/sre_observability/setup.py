"""
One-call setup for all observability components.

    from sre_observability import setup_observability, ObservabilityConfig

    cfg = ObservabilityConfig(application="payment-svc", namespace="finance")
    obs = setup_observability(cfg)
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Optional

import prometheus_client as prom

from sre_observability.metrics.runtime import RuntimeMetricsCollector
from sre_observability.tracing.setup import setup_tracing

if TYPE_CHECKING:
    from sre_observability.config import ObservabilityConfig

logger = logging.getLogger(__name__)


class Observability:
    """
    Handle returned by setup_observability().

    Provides access to sub-components and lifecycle methods.
    """

    def __init__(
        self,
        config: "ObservabilityConfig",
        runtime_collector: RuntimeMetricsCollector,
    ) -> None:
        self.config = config
        self.runtime = runtime_collector

    def shutdown(self) -> None:
        """Gracefully stop background threads."""
        self.runtime.stop()
        logger.info("Observability shut down for '%s'", self.config.application)


def setup_observability(
    config: "ObservabilityConfig",
    *,
    start_metrics_server: bool = False,
    runtime_interval: float = 15.0,
) -> Observability:
    """
    Bootstrap observability for a Python service.

    Parameters
    ----------
    config:
        ObservabilityConfig instance with application & namespace set.
    start_metrics_server:
        If True, starts a standalone HTTP server on config.metrics_port
        exposing /metrics.  Set False when the framework (FastAPI/Flask)
        serves /metrics itself.
    runtime_interval:
        How often (seconds) to refresh CPU/memory/GC gauges.

    Returns
    -------
    Observability
        Handle for accessing sub-components and shutting down.
    """
    config.validate()

    # OTel tracing
    setup_tracing(config)

    # Runtime metrics
    collector = RuntimeMetricsCollector(config, interval=runtime_interval)
    collector.start()

    # Optional standalone Prometheus HTTP server
    if start_metrics_server:
        prom.start_http_server(config.metrics_port)
        logger.info(
            "Prometheus metrics server started on :%d%s",
            config.metrics_port,
            config.metrics_path,
        )

    logger.info(
        "Observability initialised for %s/%s (env=%s ver=%s)",
        config.namespace,
        config.application,
        config.environment,
        config.version,
    )
    return Observability(config=config, runtime_collector=collector)

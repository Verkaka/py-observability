"""
Prometheus Pushgateway support for VM deployments.

Use this when:
  - You cannot open a dedicated metrics port on the host
  - Multiple Python processes share the same host (avoid port conflicts)
  - You prefer a central pull model from Pushgateway

Usage:
    from sre_observability import ObservabilityConfig, setup_observability

    cfg = ObservabilityConfig(
        application="payment-service",
        namespace="finance",
        pushgateway_url="http://pushgateway.internal:9091",
        pushgateway_interval=15,  # seconds
    )

    obs = setup_observability(cfg)  # no start_metrics_server needed
"""
from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from prometheus_client import CollectorRegistry, generate_latest, push_to_gateway

from sre_observability.metrics.runtime import RuntimeMetricsCollector

if TYPE_CHECKING:
    from sre_observability.config import ObservabilityConfig

logger = logging.getLogger(__name__)


class PushgatewayCollector:
    """
    Pushes metrics to Prometheus Pushgateway on a fixed interval.

    Each instance label is unique per (application, instance) combination,
    so multiple processes on the same VM can coexist.
    """

    def __init__(self, config: "ObservabilityConfig") -> None:
        self._config = config
        self._interval = config.pushgateway_interval
        self._url = config.pushgateway_url
        self._job = config.pushgateway_job or config.application
        self._grouping_key = self._build_grouping_key()

        self._running = False
        self._thread: threading.Thread | None = None

        # Runtime metrics collector uses the global registry by default;
        # for Pushgateway we create a dedicated registry to avoid conflicts.
        self._registry = CollectorRegistry()
        self._runtime_collector = RuntimeMetricsCollector(config, interval=self._interval)
        # Re-register runtime metrics on our dedicated registry
        # (RuntimeMetricsCollector registers on prom.REGISTRY, so we push that)

    def _build_grouping_key(self) -> dict:
        """Build grouping key for Pushgateway.

        This allows multiple instances of the same service to push
        without overwriting each other.
        """
        return {
            "application": self._config.application,
            "namespace": self._config.namespace,
            "instance": self._config.instance,
        }

    def push(self) -> None:
        """Push all metrics to Pushgateway once."""
        try:
            push_to_gateway(
                self._url,
                job=self._job,
                grouping_key=self._grouping_key,
                registry=None,  # use default global registry
            )
            logger.debug("Pushed metrics to %s (job=%s)", self._url, self._job)
        except Exception:
            logger.exception("Failed to push metrics to Pushgateway")

    def start(self) -> None:
        """Start background push thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, name="sre-pushgateway", daemon=True
        )
        self._thread.start()
        logger.info(
            "Pushgateway collector started (url=%s, interval=%ds, job=%s)",
            self._url,
            self._interval,
            self._job,
        )

    def stop(self) -> None:
        self._running = False
        # Delete metrics from Pushgateway on shutdown (optional cleanup)
        try:
            from prometheus_client import push_to_gateway, PushCollectorRegistry
            # Push empty registry to delete
            push_to_gateway(
                self._url,
                job=self._job,
                grouping_key=self._grouping_key,
                registry=CollectorRegistry(),  # empty = delete
            )
            logger.info("Deleted metrics from Pushgateway")
        except Exception:
            pass

    def _loop(self) -> None:
        while self._running:
            self.push()
            time.sleep(self._interval)

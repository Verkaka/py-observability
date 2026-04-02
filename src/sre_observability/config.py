"""
Global configuration and standard label management.

Usage:
    from sre_observability.config import ObservabilityConfig

    cfg = ObservabilityConfig(application="payment-service", namespace="finance")
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ObservabilityConfig:
    """
    Central configuration for observability.

    Required labels injected into every metric and span:
      - application : service / application name
      - namespace   : k8s namespace or logical team boundary

    Optional labels (auto-populated from env if not given):
      - environment : prod / staging / dev  (env: APP_ENV)
      - version     : release version       (env: APP_VERSION)
      - instance    : pod / host name        (env: HOSTNAME)
    """

    # --- required ---
    application: str
    namespace: str

    # --- optional (env fallback) ---
    environment: str = field(default_factory=lambda: os.getenv("APP_ENV", "unknown"))
    version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "unknown"))
    instance: str = field(default_factory=lambda: os.getenv("HOSTNAME", "unknown"))

    # --- prometheus ---
    metrics_port: int = field(default_factory=lambda: int(os.getenv("METRICS_PORT", "9090")))
    metrics_path: str = "/metrics"
    # Pushgateway mode (for VM deployments without dedicated ports)
    pushgateway_url: str | None = field(default_factory=lambda: os.getenv("PROM_PUSHGATEWAY_URL"))
    pushgateway_interval: int = field(default_factory=lambda: int(os.getenv("PROM_PUSH_INTERVAL", "15")))
    pushgateway_job: str | None = None  # defaults to application name if not set

    # --- opentelemetry ---
    otlp_endpoint: Optional[str] = field(
        default_factory=lambda: os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    )
    otel_enabled: bool = field(
        default_factory=lambda: os.getenv("OTEL_ENABLED", "true").lower() == "true"
    )
    # sampling ratio 0.0–1.0
    trace_sample_rate: float = field(
        default_factory=lambda: float(os.getenv("OTEL_TRACE_SAMPLE_RATE", "1.0"))
    )

    def base_labels(self) -> Dict[str, str]:
        """Return the standard label dict to attach to every metric."""
        return {
            "application": self.application,
            "namespace": self.namespace,
            "environment": self.environment,
            "version": self.version,
        }

    def base_attributes(self) -> Dict[str, str]:
        """Return standard OTel resource/span attributes."""
        return {
            "service.name": self.application,
            "service.namespace": self.namespace,
            "service.version": self.version,
            "deployment.environment": self.environment,
            "host.name": self.instance,
        }

    def validate(self) -> None:
        if not self.application:
            raise ValueError("ObservabilityConfig.application must not be empty")
        if not self.namespace:
            raise ValueError("ObservabilityConfig.namespace must not be empty")

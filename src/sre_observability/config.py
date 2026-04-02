"""
Global configuration and standard label management.

Usage:
    from sre_observability.config import ObservabilityConfig

    cfg = ObservabilityConfig(namespace="finance")  # application 自动取进程名
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Dict, Optional


def _get_application() -> str:
    """Get application name from Python process file name."""
    if len(sys.argv) > 0:
        import pathlib
        main_file = pathlib.Path(sys.argv[0]).name
        # Remove .py extension if present
        if main_file.endswith('.py'):
            return main_file[:-3]
        return main_file
    return "unknown"


def _get_environment(namespace: Optional[str] = None) -> str:
    """Get environment value based on namespace.

    If namespace is 'strategy', use STRATEGY_ENV env var.
    Otherwise, use ENV env var.
    """
    if namespace == "strategy":
        return os.getenv("STRATEGY_ENV", "unknown")
    return os.getenv("ENV", "unknown")


@dataclass
class ObservabilityConfig:
    """
    Central configuration for observability.

    Required labels injected into every metric and span:
      - application : auto-populated from process file name
      - namespace   : k8s namespace or logical team boundary (required)

    Optional labels (auto-populated from env if not given):
      - environment : from ENV or STRATEGY_ENV (based on namespace)
      - version     : release version       (env: APP_VERSION)
      - instance    : pod / host name        (env: HOSTNAME)
    """

    # --- required ---
    namespace: str

    # --- optional (auto-populated) ---
    application: str = field(default_factory=_get_application)

    # --- optional (env fallback) ---
    # environment is set via __post_init__ to use namespace value
    environment: str = field(default=None)  # type: ignore
    version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "unknown"))
    instance: str = field(default_factory=lambda: os.getenv("HOSTNAME", "unknown"))

    def __post_init__(self):
        if self.environment is None:
            self.environment = _get_environment(self.namespace)

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

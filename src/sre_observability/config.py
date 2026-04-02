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


def _is_containerized() -> bool:
    """Detect if running inside a container (Docker/K8s)."""
    # Check for K8s service account
    if os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount"):
        return True
    # Check for Docker socket
    if os.path.exists("/.dockerenv"):
        return True
    # Check for container runtime cgroups
    try:
        with open("/proc/1/cgroup", "r") as f:
            cgroup = f.read()
            if any(x in cgroup for x in ["docker", "kubepods", "containerd"]):
                return True
    except Exception:
        pass
    # Check environment variables
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        return True
    if os.getenv("CONTAINER_NAME") or os.getenv("DOCKER_CONTAINER"):
        return True
    return False


# Pushgateway URL mapping by environment
# SRE team manages this mapping - no need for business code to configure
_PUSHGATEWAY_URL_MAP = {
    "prod": "http://pushgateway-prod.monitoring:9091",
    "staging": "http://pushgateway-staging.monitoring:9091",
    "dev": "http://pushgateway-dev.monitoring:9091",
    "test": "http://pushgateway-dev.monitoring:9091",
    "unknown": "http://pushgateway-dev.monitoring:9091",
}


def _get_pushgateway_url(environment: str) -> str | None:
    """Get Pushgateway URL based on environment.

    Returns None if running in container (Pull mode).
    Returns mapped URL for VM deployments based on environment.
    """
    if _is_containerized():
        return None  # Container uses Pull mode
    return _PUSHGATEWAY_URL_MAP.get(environment, "http://pushgateway-dev.monitoring:9091")


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
        # Set default pushgateway_url if not provided
        if self.pushgateway_url is None:
            env_val = os.getenv("PROM_PUSHGATEWAY_URL")
            if env_val in ("", "false", "False", "none", "None"):
                self.pushgateway_url = None
            elif env_val:
                self.pushgateway_url = env_val  # Explicit override via env var
            else:
                # Auto-detect based on environment
                self.pushgateway_url = _get_pushgateway_url(self.environment)
        # Also handle explicit false values passed directly
        elif self.pushgateway_url in ("", "false", "False", "none", "None"):
            self.pushgateway_url = None

    # --- prometheus ---
    metrics_port: int = field(default_factory=lambda: int(os.getenv("METRICS_PORT", "9090")))
    metrics_path: str = "/metrics"
    # Auto-detect deployment mode (container vs VM)
    auto_metrics_mode: bool = field(default_factory=lambda: os.getenv("AUTO_METRICS_MODE", "true").lower() == "true")
    # Pushgateway URL - default set in __post_init__
    # Set PROM_PUSHGATEWAY_URL=false to disable Pushgateway mode
    pushgateway_url: str | None = field(default=None)
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

    def should_use_pushgateway(self) -> bool:
        """Determine if Pushgateway mode should be used.

        Returns True if:
        - auto_metrics_mode is True and not running in a container (default)

        Returns False if:
        - pushgateway_url is explicitly set to None or "false"
        - running in a container (auto-detection)

        Note: In container, metrics are exposed via HTTP server on :9090 (Pull mode).
              On VM, metrics are pushed to Pushgateway (Push mode).
        """
        if self.pushgateway_url is None:
            return False
        if self.auto_metrics_mode:
            return not _is_containerized()
        return False  # auto_metrics_mode=False without explicit pushgateway

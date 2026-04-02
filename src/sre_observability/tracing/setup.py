"""
OpenTelemetry tracing setup.

Configures:
  - TracerProvider with standard resource attributes
  - OTLP gRPC exporter (or console fallback when no endpoint configured)
  - ParentBased(TraceIdRatio) sampler
  - Logging integration (injects trace_id / span_id into log records)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

if TYPE_CHECKING:
    from sre_observability.config import ObservabilityConfig

logger = logging.getLogger(__name__)


def setup_tracing(config: "ObservabilityConfig") -> TracerProvider:
    """
    Initialize OpenTelemetry tracing and return the TracerProvider.

    Call this once at application startup before the first request.
    """
    if not config.otel_enabled:
        logger.info("OTel tracing disabled (OTEL_ENABLED=false)")
        return trace.get_tracer_provider()  # type: ignore[return-value]

    resource = Resource.create(config.base_attributes())

    sampler = ParentBased(root=TraceIdRatioBased(config.trace_sample_rate))
    provider = TracerProvider(resource=resource, sampler=sampler)

    if config.otlp_endpoint:
        _add_otlp_exporter(provider, config.otlp_endpoint)
        logger.info("OTel OTLP exporter → %s", config.otlp_endpoint)
    else:
        # Fallback: log spans to stdout so devs see traces locally
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("OTel no OTLP endpoint – using ConsoleSpanExporter")

    trace.set_tracer_provider(provider)
    _setup_logging_integration()

    return provider


def _add_otlp_exporter(provider: TracerProvider, endpoint: str) -> None:
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    except ImportError:
        logger.warning(
            "opentelemetry-exporter-otlp-proto-grpc not installed; "
            "falling back to ConsoleSpanExporter"
        )
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))


def _setup_logging_integration() -> None:
    """Inject trace_id and span_id into Python log records."""
    try:
        from opentelemetry.instrumentation.logging import LoggingInstrumentor

        LoggingInstrumentor().instrument(set_logging_format=True)
    except ImportError:
        pass


def get_tracer(name: str = "sre_observability") -> trace.Tracer:
    """Convenience wrapper – returns a tracer from the global provider."""
    return trace.get_tracer(name)

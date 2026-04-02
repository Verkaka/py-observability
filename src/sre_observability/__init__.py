"""
sre_observability
=================
Unified Prometheus + OpenTelemetry observability for internal Python services.

Quickstart (FastAPI)
--------------------
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from sre_observability import ObservabilityConfig, setup_observability
    from sre_observability.middleware.fastapi import instrument_fastapi

    cfg = ObservabilityConfig(application="my-svc", namespace="team-a")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        obs = setup_observability(cfg, start_metrics_server=True)
        yield
        obs.shutdown()

    app = FastAPI(lifespan=lifespan)
    instrument_fastapi(app, cfg)

Quickstart (Flask)
------------------
    from flask import Flask
    from sre_observability import ObservabilityConfig, setup_observability
    from sre_observability.middleware.flask import instrument_flask

    cfg = ObservabilityConfig(application="my-svc", namespace="team-a")
    obs = setup_observability(cfg, start_metrics_server=True)

    app = Flask(__name__)
    instrument_flask(app, cfg)
"""

from sre_observability.config import ObservabilityConfig
from sre_observability.core import ObservabilityManager, setup_observability
from sre_observability.tracing.setup import get_tracer

__all__ = [
    "ObservabilityConfig",
    "ObservabilityManager",
    "setup_observability",
    "get_tracer",
]

__version__ = "0.1.0"

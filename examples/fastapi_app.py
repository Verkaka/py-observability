"""
Example: FastAPI service with full observability.

Run:
    pip install "sre-observability[fastapi]"
    uvicorn examples.fastapi_app:app --port 8000

Metrics: GET http://localhost:8000/metrics
Traces:  set OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from sre_observability import ObservabilityConfig, setup_observability
from sre_observability.middleware.fastapi import instrument_fastapi
from sre_observability.tracing.setup import get_tracer

cfg = ObservabilityConfig(
    application="payment-service",
    namespace="finance",
    # environment / version auto-read from APP_ENV / APP_VERSION env vars
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    obs = setup_observability(cfg)
    yield
    obs.shutdown()


app = FastAPI(lifespan=lifespan)
instrument_fastapi(app, cfg)
tracer = get_tracer("payment-service")


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/pay")
async def pay(amount: float):
    with tracer.start_as_current_span("process-payment") as span:
        span.set_attribute("payment.amount", amount)
        # ... business logic ...
        return {"status": "ok", "amount": amount}


@app.get("/health")
async def health():
    return {"status": "healthy"}

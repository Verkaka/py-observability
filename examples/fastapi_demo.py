"""
FastAPI demo with async-safe metrics exposure.

Run:
    ENV=dev APP_VERSION=0.1.0 uvicorn examples.fastapi_demo:app --port 8000

Metrics available at:
    http://localhost:9090/metrics (standalone server)

Application name is auto-populated from the process file name (fastapi_demo).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from sre_observability import ObservabilityConfig, setup_observability
from sre_observability.middleware.fastapi import instrument_fastapi


cfg = ObservabilityConfig(
    namespace="finance",  # application auto-populated from process name
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start metrics server on port 9090 (async-safe, no blocking)
    obs = setup_observability(cfg, start_metrics_server=True)
    yield
    obs.shutdown()


app = FastAPI(lifespan=lifespan)
instrument_fastapi(app, cfg)


@app.get("/")
async def root():
    return {"status": "ok", "service": cfg.application}


@app.get("/pay/{amount}")
async def pay(amount: float):
    # Simulate payment processing
    import asyncio
    await asyncio.sleep(0.05)
    return {"status": "success", "amount": amount, "currency": "USD"}


@app.get("/health")
async def health():
    return {"healthy": True}

"""
Example: Flask service with full observability.

Run:
    pip install "sre-observability[flask]"
    flask --app examples.flask_app run --port 8000

Metrics: GET http://localhost:9090/metrics  (standalone server on port 9090)
"""
from flask import Flask, jsonify

from sre_observability import ObservabilityConfig, setup_observability
from sre_observability.middleware.flask import instrument_flask
from sre_observability.tracing.setup import get_tracer

cfg = ObservabilityConfig(
    application="order-service",
    namespace="commerce",
)

# start_metrics_server=True → Prometheus HTTP server on cfg.metrics_port (9090)
obs = setup_observability(cfg, start_metrics_server=True)

app = Flask(__name__)
instrument_flask(app, cfg)
tracer = get_tracer("order-service")


@app.get("/orders/<int:order_id>")
def get_order(order_id: int):
    with tracer.start_as_current_span("fetch-order") as span:
        span.set_attribute("order.id", order_id)
        return jsonify({"order_id": order_id, "status": "shipped"})


@app.get("/health")
def health():
    return jsonify({"status": "healthy"})

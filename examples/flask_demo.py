"""
Flask demo with standalone metrics server.

Run:
    APP_ENV=dev APP_VERSION=0.1.0 flask --app examples.flask_demo run --port 8000

Metrics available at:
    http://localhost:9090/metrics
"""
from flask import Flask, jsonify

from sre_observability import ObservabilityConfig, setup_observability
from sre_observability.middleware.flask import instrument_flask


cfg = ObservabilityConfig(
    application="order-service",
    namespace="commerce",
)

obs = setup_observability(cfg, start_metrics_server=True)

app = Flask(__name__)
instrument_flask(app, cfg)


@app.get("/")
def root():
    return jsonify({"status": "ok", "service": cfg.application})


@app.get("/orders/<int:order_id>")
def get_order(order_id: int):
    import time
    time.sleep(0.02)
    return jsonify({"order_id": order_id, "status": "shipped"})


@app.get("/health")
def health():
    return jsonify({"healthy": True})

"""
Flask demo with Pushgateway mode (for VM deployments).

Use this when you cannot open a dedicated metrics port on the host.

Run:
    APP_ENV=dev APP_VERSION=0.1.0 \
    PROM_PUSHGATEWAY_URL=http://localhost:9091 \
    flask --app examples.flask_pushgateway run --port 8000

Metrics will be pushed to Pushgateway every 15 seconds.
"""
from flask import Flask, jsonify

from sre_observability import ObservabilityConfig, setup_observability
from sre_observability.middleware.flask import instrument_flask


cfg = ObservabilityConfig(
    application="order-service",
    namespace="commerce",
    # Pushgateway URL (or set via env: PROM_PUSHGATEWAY_URL)
    pushgateway_url="http://localhost:9091",
    pushgateway_interval=15,
    # Optional: customize job name (defaults to application)
    pushgateway_job="python-service",
)

# No start_metrics_server=True needed - metrics are pushed!
obs = setup_observability(cfg)

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

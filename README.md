# sre-observability

统一 Python 服务的 Prometheus + OpenTelemetry 可观测性接入，由 SRE 团队维护。

一行代码完成接入，自动采集运行时指标和 HTTP 接口指标，强制注入标准 label。

---

## 目录

- [功能概览](#功能概览)
- [安装](#安装)
- [快速开始](#快速开始)
  - [FastAPI](#fastapi)
  - [Flask](#flask)
- [配置参考](#配置参考)
- [指标说明](#指标说明)
  - [运行时指标](#运行时指标)
  - [HTTP 接口指标](#http-接口指标)
- [OpenTelemetry Tracing](#opentelemetry-tracing)
- [标准 Label 规范](#标准-label-规范)
- [Prometheus 采集配置](#prometheus-采集配置)
- [Grafana 面板查询参考](#grafana-面板查询参考)
- [开发与贡献](#开发与贡献)

---

## 功能概览

| 能力 | 说明 |
|---|---|
| **标准 Label** | 所有指标自动注入 `application` / `namespace` / `environment` / `version` |
| **运行时指标** | CPU、内存（RSS/VMS）、线程数、文件描述符、GC、进程存活时长 |
| **HTTP 指标** | 请求总数、耗时直方图（P50/P95/P99）、实时并发数，按路由模板聚合 |
| **OpenTelemetry** | Trace 自动上报 OTLP，Resource 属性对齐 label 规范，trace_id 注入日志 |
| **框架中间件** | FastAPI 和 Flask 开箱即用，无需手动埋点 |
| **零侵入** | 仅需在启动处调用一次 `setup_observability()` |

---

## 安装

```bash
# FastAPI 项目
pip install "sre-observability[fastapi]"

# Flask 项目
pip install "sre-observability[flask]"

# 全部可选依赖（含 requests 自动追踪）
pip install "sre-observability[all]"
```

> **内部 PyPI**：`pip install sre-observability --index-url https://pypi.internal.company.com/simple`

---

## 快速开始

### FastAPI

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

from sre_observability import ObservabilityConfig, setup_observability
from sre_observability.middleware.fastapi import instrument_fastapi

# 1. 声明服务身份（必填：application、namespace）
cfg = ObservabilityConfig(
    application="payment-service",
    namespace="finance",
)

# 2. 在 lifespan 中初始化，启用独立 metrics server（异步安全）
@asynccontextmanager
async def lifespan(app: FastAPI):
    obs = setup_observability(cfg, start_metrics_server=True)
    yield
    obs.shutdown()

app = FastAPI(lifespan=lifespan)

# 3. 挂载中间件（自动统计所有接口的请求数和耗时）
instrument_fastapi(app, cfg)

# 业务接口，无需任何修改
@app.get("/pay")
async def pay(amount: float):
    return {"status": "ok", "amount": amount}
```

启动：

```bash
APP_ENV=prod APP_VERSION=1.2.0 uvicorn main:app --host 0.0.0.0 --port 8000
```

访问 `http://localhost:9090/metrics` 即可看到全部指标。

---

### Flask

```python
from flask import Flask, jsonify

from sre_observability import ObservabilityConfig, setup_observability
from sre_observability.middleware.flask import instrument_flask

cfg = ObservabilityConfig(
    application="order-service",
    namespace="commerce",
)

# start_metrics_server=True：在独立端口（默认 9090）启动 Prometheus HTTP server
# 适合 Flask 不方便直接暴露 /metrics 的场景
obs = setup_observability(cfg, start_metrics_server=True)

app = Flask(__name__)

# 挂载中间件
instrument_flask(app, cfg)

@app.get("/orders/<int:order_id>")
def get_order(order_id: int):
    return jsonify({"order_id": order_id, "status": "shipped"})
```

启动：

```bash
APP_ENV=prod APP_VERSION=1.0.0 flask --app main run --port 8000
# Prometheus 指标在 :9090/metrics
```

---

### Pushgateway 模式（虚拟机部署推荐）

```python
from flask import Flask, jsonify

from sre_observability import ObservabilityConfig, setup_observability
from sre_observability.middleware.flask import instrument_flask

cfg = ObservabilityConfig(
    application="order-service",
    namespace="commerce",
    # Pushgateway URL（或通过环境变量 PROM_PUSHGATEWAY_URL）
    pushgateway_url="http://pushgateway.internal:9091",
    pushgateway_interval=15,  # 推送间隔（秒）
)

# 不需要 start_metrics_server=True，指标会自动推送！
obs = setup_observability(cfg)

app = Flask(__name__)
instrument_flask(app, cfg)
```

启动：

```bash
APP_ENV=prod APP_VERSION=1.0.0 \
PROM_PUSHGATEWAY_URL=http://pushgateway.internal:9091 \
flask --app main run --port 8000
```

指标会通过 Pushgateway 统一采集，无需在每台 VM 上开放端口。

---

## 配置参考

`ObservabilityConfig` 支持构造参数和环境变量两种方式，优先使用构造参数。

| 参数 | 类型 | 必填 | 环境变量 | 默认值 | 说明 |
|---|---|---|---|---|---|
| `application` | str | ✅ | — | — | 服务名，如 `payment-service` |
| `namespace` | str | ✅ | — | — | k8s namespace 或业务域 |
| `environment` | str | | `APP_ENV` | `unknown` | `prod` / `staging` / `dev` |
| `version` | str | | `APP_VERSION` | `unknown` | 服务版本号 |
| `instance` | str | | `HOSTNAME` | 主机名 | Pod 名 / 实例标识 |
| `metrics_port` | int | | `METRICS_PORT` | `9090` | 独立 metrics server 端口 |
| `pushgateway_url` | str | | `PROM_PUSHGATEWAY_URL` | `None` | Pushgateway 地址（VM 部署用） |
| `pushgateway_interval` | int | | `PROM_PUSH_INTERVAL` | `15` | Pushgateway 推送间隔（秒） |
| `pushgateway_job` | str | | — | `application` | Pushgateway job 名 |
| `otlp_endpoint` | str | | `OTEL_EXPORTER_OTLP_ENDPOINT` | `None` | OTLP gRPC 地址，如 `http://jaeger:4317` |
| `otel_enabled` | bool | | `OTEL_ENABLED` | `true` | 是否启用 OTel tracing |
| `trace_sample_rate` | float | | `OTEL_TRACE_SAMPLE_RATE` | `1.0` | 采样率，0.0–1.0 |

**推荐做法**：在代码中只填 `application` 和 `namespace`，其余通过部署平台的环境变量注入，做到代码与环境无关。

```python
# 代码中（不含环境信息）
cfg = ObservabilityConfig(application="payment-service", namespace="finance")

# Kubernetes Deployment 中注入
env:
  - name: APP_ENV
    value: prod
  - name: APP_VERSION
    valueFrom:
      fieldRef:
        fieldPath: metadata.labels['version']
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: "http://otel-collector.monitoring:4317"
```

---

## 指标说明

### 运行时指标

每 15 秒（可配置）采集一次，反映 Python 进程自身的健康状态。

| 指标名 | 类型 | 说明 |
|---|---|---|
| `process_cpu_usage_percent` | Gauge | 进程 CPU 使用率（%），多核环境可超过 100 |
| `process_memory_rss_bytes` | Gauge | 常驻内存（RSS），实际物理内存占用 |
| `process_memory_vms_bytes` | Gauge | 虚拟内存大小 |
| `process_memory_percent` | Gauge | 占系统总内存的百分比 |
| `process_thread_count` | Gauge | 当前线程数 |
| `process_open_fds` | Gauge | 打开的文件描述符数量 |
| `process_gc_objects_total` | Gauge | GC 追踪对象总数 |
| `process_gc_collections_total` | Counter | GC 回收次数，按 `generation` 分代统计 |
| `process_uptime_seconds_total` | Counter | 进程运行时长（秒） |

所有运行时指标均携带 `application` / `namespace` / `environment` / `version` 四个 label。

---

### HTTP 接口指标

由中间件自动采集，**无需在每个接口手动埋点**。

| 指标名 | 类型 | Label | 说明 |
|---|---|---|---|
| `http_requests_total` | Counter | method, route, status_code + 基础 4 个 | 请求总数 |
| `http_request_duration_seconds` | Histogram | 同上 | 请求耗时，含 P50/P95/P99 分位数 |
| `http_requests_in_flight` | Gauge | method, route + 基础 4 个 | 当前正在处理的请求数 |

**`route` label 使用路由模板**（如 `/users/{id}`）而非实际 URL（如 `/users/42`），避免高基数导致 Prometheus 性能问题。

Histogram 分桶（秒）：`0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0`

**查询示例**：

```promql
# 接口 QPS（过去 1 分钟）
rate(http_requests_total{application="payment-service"}[1m])

# P99 延迟
histogram_quantile(0.99,
  rate(http_request_duration_seconds_bucket{application="payment-service"}[5m])
)

# 错误率（非 2xx 占比）
sum(rate(http_requests_total{application="payment-service", status_code!~"2.."}[5m]))
/
sum(rate(http_requests_total{application="payment-service"}[5m]))

# 当前并发
http_requests_in_flight{application="payment-service"}
```

---

## OpenTelemetry Tracing

### 自动上报

配置 `OTEL_EXPORTER_OTLP_ENDPOINT` 后，trace 自动通过 OTLP gRPC 上报，无需额外代码：

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
```

未配置时降级为 `ConsoleSpanExporter`，在标准输出打印 span，方便本地调试。

### 手动创建 Span

```python
from sre_observability import get_tracer

tracer = get_tracer("payment-service")

@app.get("/pay")
async def pay(amount: float):
    with tracer.start_as_current_span("process-payment") as span:
        span.set_attribute("payment.amount", amount)
        span.set_attribute("payment.currency", "CNY")
        result = do_payment(amount)
        return result
```

### Trace ID 注入日志

`setup_observability()` 调用后，Python 标准日志自动携带 `trace_id` 和 `span_id`：

```
INFO [app.payment] [trace_id=4bf92f3577b34da6 span_id=00f067aa0ba902b7] - Processing payment amount=99.5
```

方便在 Grafana 中通过 trace_id 从日志跳转到 Jaeger 链路图。

### 采样率

生产环境流量大时可降低采样率，减少 Jaeger 存储压力：

```python
# 仅采样 10% 的请求
cfg = ObservabilityConfig(
    application="high-traffic-service",
    namespace="api",
    trace_sample_rate=0.1,
)

# 或通过环境变量
# OTEL_TRACE_SAMPLE_RATE=0.1
```

---

## 标准 Label 规范

SRE 团队规定所有内部服务的 Prometheus 指标**必须**携带以下 4 个 label，本包强制注入，无法关闭：

| Label | 值示例 | 用途 |
|---|---|---|
| `application` | `payment-service` | 区分同 namespace 下不同服务 |
| `namespace` | `finance` | 对应 k8s namespace，按团队/业务域聚合告警 |
| `environment` | `prod` / `staging` | 隔离生产和非生产数据 |
| `version` | `1.2.0` | 版本对比，发现发布引入的性能回退 |

**注意**：不要在业务代码中自行添加高基数 label（如 user_id、request_id），会导致 Prometheus 内存暴涨。如需追踪单请求，使用 OTel Tracing。

---

## 两种采集模式对比

本包支持 **Pull（独立 HTTP Server）** 和 **Push（Pushgateway）** 两种模式，可根据部署环境选择。

### 架构对比

| 模式 | 架构图 | 适用场景 |
|---|---|---|
| **Pull（独立端口）** | `App :9090/metrics` ← Prometheus scrape | 容器化部署（K8s）、可开放端口的 VM |
| **Push（Pushgateway）** | `App → Push :9091` ← Prometheus scrape Pushgateway | 共享 VM、端口受限、临时任务 |

### 详细对比

| 维度 | Pull 模式（独立 HTTP Server） | Pushgateway 模式 |
|---|---|---|
| **端口需求** | 每台 VM 需开放独立端口（如 9090） | 只需 Pushgateway 一个端口 |
| **端口冲突风险** | 多进程同机部署时需手动分配不同端口 | 无冲突风险 |
| **部署复杂度** | 低（内置 HTTP 服务器） | 中（需额外维护 Pushgateway 服务） |
| **实时性** | 实时（Prometheus 按需抓取） | 有延迟（取决于推送间隔，默认 15s） |
| **服务下线处理** | 自动失效（scrape 失败） | 需主动删除指标（包会自动 cleanup） |
| **网络要求** | Prometheus 需能访问所有 VM | 只需 VM 能访问 Pushgateway |
| **扩缩容适应性** | 需配合服务发现（K8s SD/Consul 等） | 天然支持（Pushgateway 聚合） |
| **运维成本** | 低 | 中（Pushgateway 本身需高可用 + 存储） |

### 选型建议

**选择 Pull 模式（`start_metrics_server=True`）**：

- 已容器化部署在 K8s
- VM 独享且可开放端口
- 希望减少外部依赖

**选择 Pushgateway 模式（`pushgateway_url=...`）**：

- 多 Python 进程共享同一 VM（端口冲突风险）
- 网络隔离导致 Prometheus 无法直连应用
- 临时任务 / 批处理作业（job 结束后指标可清理）

### 代码差异

```python
# Pull 模式
cfg = ObservabilityConfig(application="svc", namespace="team")
obs = setup_observability(cfg, start_metrics_server=True)  # 监听 9090

# Push 模式
cfg = ObservabilityConfig(
    application="svc",
    namespace="team",
    pushgateway_url="http://pushgateway:9091",
)
obs = setup_observability(cfg)  # 无需 start_metrics_server
```

---

## Prometheus 采集配置

在 Prometheus `scrape_configs` 中添加：

```yaml
scrape_configs:
  - job_name: "python-services"
    scrape_interval: 15s
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      # 只抓取标注了 prometheus.io/scrape=true 的 Pod
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: "true"
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_port]
        action: replace
        target_label: __address__
        regex: (.+)
        replacement: $1
```

在 Kubernetes Deployment 中添加注解：

```yaml
metadata:
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "9090"    # 独立 metrics server 端口
    prometheus.io/path: "/metrics"
```

---

## Grafana 面板查询参考

### 服务总览 Dashboard

```promql
# 请求量（按路由分）
sum by (route) (rate(http_requests_total{application="$application", environment="$env"}[5m]))

# P99 延迟（按路由分）
histogram_quantile(0.99,
  sum by (route, le) (
    rate(http_request_duration_seconds_bucket{application="$application", environment="$env"}[5m])
  )
)

# 错误率
sum(rate(http_requests_total{application="$application", environment="$env", status_code=~"5.."}[5m]))
/
sum(rate(http_requests_total{application="$application", environment="$env"}[5m]))

# 内存使用趋势
process_memory_rss_bytes{application="$application", environment="$env"}

# GC 回收频率
rate(process_gc_collections_total{application="$application", generation="0"}[5m])
```

### 推荐告警规则

```yaml
groups:
  - name: python-service-alerts
    rules:
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{status_code=~"5.."}[5m])) by (application, namespace)
          /
          sum(rate(http_requests_total[5m])) by (application, namespace)
          > 0.05
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "{{ $labels.application }} 错误率超过 5%"

      - alert: HighP99Latency
        expr: |
          histogram_quantile(0.99,
            rate(http_request_duration_seconds_bucket[5m])
          ) > 1.0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "{{ $labels.application }} P99 延迟超过 1s"

      - alert: HighMemoryUsage
        expr: process_memory_percent > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "{{ $labels.application }} 内存使用率超过 80%"
```

---

## 开发与贡献

```bash
git clone https://git.internal.company.com/sre/py-observability.git
cd py-observability
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"

# 运行 FastAPI demo
APP_ENV=dev APP_VERSION=0.1.0 uvicorn examples.fastapi_app:app --port 8000

# 运行 Flask demo
APP_ENV=dev APP_VERSION=0.1.0 flask --app examples.flask_app run --port 8000
```

新增框架支持（如 gRPC、Celery）参考 `src/sre_observability/middleware/` 目录下的现有实现，在 `HttpMetrics` 基础上封装即可复用相同的 label 注入逻辑。

如有问题请联系 SRE 团队或在内部 issue tracker 提交工单。

"""
Strategy Metrics - 策略业务指标

除了基础的 CPU/内存指标外，量化策略需要特定的业务指标：
- 交易次数
- 盈亏 (PnL)
- 持仓情况
- 信号延迟
- 订单成功率
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import prometheus_client as prom

if TYPE_CHECKING:
    from sre_observability.config import ObservabilityConfig

logger = logging.getLogger(__name__)

# 策略指标 label
_STRATEGY_LABEL_NAMES = [
    "application",  # 策略 ID
    "namespace",    # 团队
    "environment",
    "version",
    "strategy_id",  # 同 application
    "team",         # 同 namespace
    "symbol",       # 交易对
    "side",         # buy/sell
]

_PNL_LABEL_NAMES = [
    "application", "namespace", "environment", "version",
    "strategy_id", "team", "symbol",
]


class StrategyMetrics:
    """
    策略业务指标收集

    用法:
        metrics = StrategyMetrics(cfg)
        metrics.record_trade("BTCUSDT", "buy", 100, 0.5)
        metrics.record_pnl("BTCUSDT", 250.5)
    """

    _instance: "StrategyMetrics | None" = None

    def __new__(cls, config: "ObservabilityConfig") -> "StrategyMetrics":
        if cls._instance is None:
            obj = super().__new__(cls)
            obj._initialized = False
            cls._instance = obj
        return cls._instance

    def __init__(self, config: "ObservabilityConfig") -> None:
        if self._initialized:
            return

        self._config = config
        self._base_labels = {
            "application": config.application,
            "namespace": config.namespace,
            "environment": config.environment,
            "version": config.version,
            "strategy_id": config.application,  # alias
            "team": config.namespace,  # alias
        }

        self._init_metrics()
        self._initialized = True

    def _init_metrics(self) -> None:
        # 交易计数器
        self.trades_total = prom.Counter(
            "strategy_trades_total",
            "Total number of trades executed",
            labelnames=_STRATEGY_LABEL_NAMES,
            registry=prom.REGISTRY,
        )

        # 交易金额
        self.trade_volume = prom.Counter(
            "strategy_trade_volume",
            "Total trade volume in quote currency",
            labelnames=_STRATEGY_LABEL_NAMES,
            registry=prom.REGISTRY,
        )

        # 盈亏 (PnL)
        self.pnl = prom.Gauge(
            "strategy_pnl",
            "Profit and Loss in quote currency",
            labelnames=_PNL_LABEL_NAMES,
            registry=prom.REGISTRY,
        )

        # 累计盈亏
        self.pnl_cumulative = prom.Counter(
            "strategy_pnl_cumulative",
            "Cumulative PnL",
            labelnames=_PNL_LABEL_NAMES,
            registry=prom.REGISTRY,
        )

        # 持仓
        self.position = prom.Gauge(
            "strategy_position",
            "Current position size",
            labelnames=_PNL_LABEL_NAMES,
            registry=prom.REGISTRY,
        )

        # 订单延迟 (信号到下单)
        self.order_latency = prom.Histogram(
            "strategy_order_latency_seconds",
            "Latency from signal to order placement",
            labelnames=list(self._base_labels.keys()),
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
            registry=prom.REGISTRY,
        )

        # 订单成功率
        self.orders_success = prom.Counter(
            "strategy_orders_success_total",
            "Successful orders count",
            labelnames=list(self._base_labels.keys()),
            registry=prom.REGISTRY,
        )

        self.orders_failed = prom.Counter(
            "strategy_orders_failed_total",
            "Failed orders count",
            labelnames=list(self._base_labels.keys()) + ["error_type"],
            registry=prom.REGISTRY,
        )

        # 信号延迟
        self.signal_latency = prom.Histogram(
            "strategy_signal_latency_seconds",
            "Latency from market data to signal generation",
            labelnames=list(self._base_labels.keys()),
            buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5),
            registry=prom.REGISTRY,
        )

        # 策略运行状态
        self.strategy_status = prom.Gauge(
            "strategy_status",
            "Strategy running status (1=running, 0=stopped, -1=error)",
            labelnames=list(self._base_labels.keys()),
            registry=prom.REGISTRY,
        )

        # 心跳
        self.strategy_heartbeat = prom.Gauge(
            "strategy_heartbeat_timestamp",
            "Last heartbeat timestamp",
            labelnames=list(self._base_labels.keys()),
            registry=prom.REGISTRY,
        )

    # -------------------- 指标记录方法 --------------------

    def record_trade(
        self,
        symbol: str,
        side: str,
        volume: float,
        price: float,
    ) -> None:
        """记录交易"""
        labels = {**self._base_labels, "symbol": symbol, "side": side}
        self.trades_total.labels(**labels).inc()
        self.trade_volume.labels(**labels).inc(volume * price)

    def record_pnl(self, symbol: str, pnl: float) -> None:
        """记录盈亏"""
        labels = {**self._base_labels, "symbol": symbol}
        self.pnl.labels(**labels).set(pnl)
        if pnl > 0:
            self.pnl_cumulative.labels(**labels).inc(pnl)

    def record_position(self, symbol: str, position: float) -> None:
        """记录持仓"""
        labels = {**self._base_labels, "symbol": symbol}
        self.position.labels(**labels).set(position)

    def record_order_latency(self, latency_seconds: float) -> None:
        """记录订单延迟"""
        self.order_latency.labels(**self._base_labels).observe(latency_seconds)

    def record_signal_latency(self, latency_seconds: float) -> None:
        """记录信号延迟"""
        self.signal_latency.labels(**self._base_labels).observe(latency_seconds)

    def record_order_success(self) -> None:
        """记录成功订单"""
        self.orders_success.labels(**self._base_labels).inc()

    def record_order_failed(self, error_type: str = "unknown") -> None:
        """记录失败订单"""
        labels = {**self._base_labels, "error_type": error_type}
        self.orders_failed.labels(**labels).inc()

    def set_status(self, status: int) -> None:
        """设置策略状态 (1=running, 0=stopped, -1=error)"""
        self.strategy_status.labels(**self._base_labels).set(status)
        if status == 1:
            self.strategy_heartbeat.labels(**self._base_labels).set_to_current_time()

    def heartbeat(self) -> None:
        """发送心跳"""
        self.strategy_heartbeat.labels(**self._base_labels).set_to_current_time()


# 全局实例
_metrics: StrategyMetrics | None = None


def init_strategy_metrics(config: "ObservabilityConfig") -> StrategyMetrics:
    """初始化策略指标"""
    global _metrics
    _metrics = StrategyMetrics(config)
    return _metrics


def get_strategy_metrics() -> StrategyMetrics | None:
    """获取全局策略指标实例"""
    return _metrics

"""
Strategy Context - 策略上下文管理器

提供统一的策略运行上下文，整合注册、指标、告警功能。
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from sre_observability.strategy.registry import init_registry, get_registry, StrategyRegistry
from sre_observability.strategy.metrics import init_strategy_metrics, get_strategy_metrics, StrategyMetrics
from sre_observability.strategy.alerts import AlertConfig, PredefinedAlerts, StrategyAlerter

if TYPE_CHECKING:
    from sre_observability.config import ObservabilityConfig

logger = logging.getLogger(__name__)


@dataclass
class TradeContext:
    """交易上下文"""
    symbol: str
    side: str
    volume: float
    price: float
    start_time: float = field(default_factory=time.time)
    success: bool = True
    error_type: str = ""


class StrategyContext:
    """
    策略运行上下文

    用法:
        ctx = StrategyContext(cfg, strategy_id="btc_arb_v1", ...)
        ctx.start()

        while running:
            with ctx.track_trade("BTCUSDT", "buy", 1.0, 50000):
                execute_trade(...)
    """

    def __init__(
        self,
        config: "ObservabilityConfig",
        strategy_id: str,
        strategy_name: str,
        team: str,
        owner: str,
        alert_webhook_url: Optional[str] = None,
    ):
        self.config = config
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        self.team = team
        self.owner = owner
        self.alert_webhook_url = alert_webhook_url

        self._registry: Optional[StrategyRegistry] = None
        self._metrics: Optional[StrategyMetrics] = None
        self._alerter: Optional[StrategyAlerter] = None

        self._running = False
        self._last_heartbeat = 0

    def start(self) -> None:
        """启动策略上下文"""
        logger.info(f"Starting strategy context: {self.strategy_id}")

        # 1. 注册策略
        self._registry = init_registry(
            strategy_id=self.strategy_id,
            strategy_name=self.strategy_name,
            team=self.team,
            owner=self.owner,
        )

        # 2. 初始化指标
        self._metrics = init_strategy_metrics(self.config)
        self._metrics.set_status(1)  # running

        # 3. 初始化告警器
        if self.alert_webhook_url:
            alert_config = AlertConfig(
                alert_name=f"StrategyAlert-{self.strategy_id}",
                description=f"Alerts for strategy {self.strategy_name}",
                webhook_url=self.alert_webhook_url,
                labels={
                    "strategy_id": self.strategy_id,
                    "team": self.team,
                },
            )
            self._alerter = StrategyAlerter(alert_config)

        self._running = True
        logger.info(f"Strategy context started: {self.strategy_id}")

    def stop(self, error: bool = False) -> None:
        """停止策略上下文"""
        logger.info(f"Stopping strategy context: {self.strategy_id}")

        self._running = False

        if self._metrics:
            self._metrics.set_status(-1 if error else 0)

        if self._registry:
            self._registry.unregister()

        logger.info(f"Strategy context stopped: {self.strategy_id}")

    def heartbeat(self) -> None:
        """发送心跳"""
        if self._metrics:
            self._metrics.heartbeat()
        if self._registry:
            self._registry.heartbeat()
        self._last_heartbeat = time.time()

    @contextmanager
    def track_trade(self, symbol: str, side: str, volume: float, price: float):
        """
        跟踪交易的上下文管理器

        用法:
            with ctx.track_trade("BTCUSDT", "buy", 1.0, 50000):
                execute_trade(...)
        """
        start = time.time()
        success = True
        error_type = ""

        try:
            yield
        except Exception as e:
            success = False
            error_type = type(e).__name__
            logger.error(f"Trade failed: {e}")
            if self._metrics:
                self._metrics.record_order_failed(error_type)
            if self._alerter:
                self._alerter.send_alert(
                    "交易执行失败",
                    {"symbol": symbol, "side": side, "error": str(e)},
                    severity="warning",
                )
        finally:
            elapsed = time.time() - start
            if self._metrics:
                self._metrics.record_order_latency(elapsed)
                if success:
                    self._metrics.record_trade(symbol, side, volume, price)
                    self._metrics.record_order_success()

    @contextmanager
    def track_signal(self):
        """
        跟踪信号生成的上下文管理器

        用法:
            with ctx.track_signal():
                signal = generate_signal(data)
        """
        start = time.time()
        try:
            yield
        finally:
            elapsed = time.time() - start
            if self._metrics:
                self._metrics.record_signal_latency(elapsed)

    def record_pnl(self, symbol: str, pnl: float) -> None:
        """记录盈亏"""
        if self._metrics:
            self._metrics.record_pnl(symbol, pnl)

            # 亏损告警
            if pnl < -1000:  # 阈值示例
                if self._alerter:
                    self._alerter.send_alert(
                        "大额亏损",
                        {"symbol": symbol, "pnl": pnl},
                        severity="critical",
                    )

    def record_position(self, symbol: str, position: float) -> None:
        """记录持仓"""
        if self._metrics:
            self._metrics.record_position(symbol, position)

    @property
    def is_running(self) -> bool:
        return self._running


# Convenience function
def init_strategy(
    strategy_id: str,
    strategy_name: str,
    team: str,
    owner: str,
    namespace: str,
    environment: Optional[str] = None,
    version: str = "1.0.0",
    alert_webhook_url: Optional[str] = None,
) -> StrategyContext:
    """
    初始化策略上下文

    Args:
        strategy_id: 策略唯一标识
        strategy_name: 策略名称
        team: 所属团队
        owner: 负责人
        namespace: Prometheus namespace (通常与 team 相同)
        environment: 环境 (prod/staging/dev)
        version: 策略版本
        alert_webhook_url: 告警平台 Webhook URL

    Returns:
        StrategyContext 实例
    """
    from sre_observability.config import ObservabilityConfig

    cfg = ObservabilityConfig(
        namespace=namespace,
        application=strategy_id,  # 会被自动覆盖为进程名，但这里显式设置
        environment=environment,
        version=version,
    )

    ctx = StrategyContext(
        config=cfg,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        team=team,
        owner=owner,
        alert_webhook_url=alert_webhook_url,
    )

    ctx.start()
    return ctx

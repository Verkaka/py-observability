"""
Strategy Alerts - 策略告警规则

预定义的告警规则模板，支持：
- 策略异常停止
- 订单失败率过高
- 延迟过高
- 亏损超阈值
- 心跳丢失
"""
from __future__ import annotations

import logging
import os
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AlertConfig:
    """告警配置"""
    # 基础配置
    alert_name: str
    description: str
    severity: str = "warning"  # info, warning, critical

    # 告警平台 Webhook
    webhook_url: str = field(default_factory=lambda: os.getenv("ALERT_WEBHOOK_URL", ""))

    # 额外标签
    labels: dict = field(default_factory=dict)

    # 抑制配置
    for_duration: int = 60  # 持续多少秒后告警
    cooldown: int = 300  # 告警冷却时间 (秒)


class StrategyAlerter:
    """
    策略告警器

    用法:
        alerter = StrategyAlerter(alert_config)
        alerter.send_alert("策略异常停止", {"strategy_id": "btc_arb_v1"})
    """

    def __init__(self, config: AlertConfig):
        self.config = config
        self._last_alert: dict = {}  # 记录上次告警时间

    def send_alert(
        self,
        alert_title: str,
        context: dict,
        severity: Optional[str] = None,
    ) -> bool:
        """
        发送告警到告警平台

        Args:
            alert_title: 告警标题
            context: 告警上下文信息
            severity: 告警级别

        Returns:
            是否发送成功
        """
        # 检查冷却时间
        alert_key = f"{self.config.alert_name}:{alert_title}"
        import time
        now = time.time()

        if alert_key in self._last_alert:
            elapsed = now - self._last_alert[alert_key]
            if elapsed < self.config.cooldown:
                logger.debug(f"Alert in cooldown: {alert_title}")
                return False

        # 构建告警 payload
        payload = self._build_payload(alert_title, context, severity)

        # 发送到告警平台
        success = self._send_to_platform(payload)

        if success:
            self._last_alert[alert_key] = now

        return success

    def _build_payload(
        self,
        alert_title: str,
        context: dict,
        severity: Optional[str] = None,
    ) -> dict:
        """构建告警 payload"""
        return {
            "alert_name": self.config.alert_name,
            "title": alert_title,
            "description": self.config.description,
            "severity": severity or self.config.severity,
            "labels": {
                **self.config.labels,
                **context,
            },
            "annotations": {
                "summary": f"{alert_title}: {context.get('strategy_id', 'unknown')}",
                "description": self.config.description,
            },
            "timestamp": int(time.time() * 1000),
        }

    def _send_to_platform(self, payload: dict) -> bool:
        """发送到告警平台"""
        if not self.config.webhook_url:
            logger.warning("No webhook URL configured, skipping alert")
            return False

        try:
            import json
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.config.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                logger.info(f"Alert sent: {resp.status}")
                return True
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
            return False


# -------------------- 预定义告警规则 --------------------

class PredefinedAlerts:
    """预定义告警规则工厂"""

    @staticmethod
    def strategy_stopped(config_base: AlertConfig) -> StrategyAlerter:
        """策略异常停止告警"""
        return StrategyAlerter(AlertConfig(
            alert_name="StrategyStopped",
            description="策略进程异常退出或心跳丢失",
            severity="critical",
            webhook_url=config_base.webhook_url,
            labels={"alert_type": "strategy_stopped"},
            for_duration=30,
            cooldown=60,
        ))

    @staticmethod
    def high_order_failure_rate(config_base: AlertConfig) -> StrategyAlerter:
        """订单失败率过高告警"""
        return StrategyAlerter(AlertConfig(
            alert_name="HighOrderFailureRate",
            description="订单失败率超过阈值 (10%)",
            severity="warning",
            webhook_url=config_base.webhook_url,
            labels={"alert_type": "order_failure"},
            for_duration=60,
            cooldown=300,
        ))

    @staticmethod
    def high_latency(config_base: AlertConfig) -> StrategyAlerter:
        """延迟过高告警"""
        return StrategyAlerter(AlertConfig(
            alert_name="HighLatency",
            description="订单延迟超过阈值 (100ms)",
            severity="warning",
            webhook_url=config_base.webhook_url,
            labels={"alert_type": "high_latency"},
            for_duration=120,
            cooldown=300,
        ))

    @staticmethod
    def high_loss(config_base: AlertConfig) -> StrategyAlerter:
        """亏损超阈值告警"""
        return StrategyAlerter(AlertConfig(
            alert_name="HighLoss",
            description="策略亏损超过阈值",
            severity="critical",
            webhook_url=config_base.webhook_url,
            labels={"alert_type": "high_loss"},
            for_duration=0,  # 立即告警
            cooldown=600,
        ))

    @staticmethod
    def heartbeat_lost(config_base: AlertConfig) -> StrategyAlerter:
        """心跳丢失告警"""
        return StrategyAlerter(AlertConfig(
            alert_name="HeartbeatLost",
            description="策略心跳丢失超过 60 秒",
            severity="critical",
            webhook_url=config_base.webhook_url,
            labels={"alert_type": "heartbeat_lost"},
            for_duration=60,
            cooldown=60,
        ))


# -------------------- Prometheus Alertmanager 规则模板 --------------------

ALERTMANAGER_RULES_TEMPLATE = """
groups:
  - name: strategy-alerts
    rules:
      # 策略心跳丢失
      - alert: StrategyHeartbeatLost
        expr: (time() - strategy_heartbeat_timestamp) > 60
        for: 30s
        labels:
          severity: critical
          alert_type: heartbeat_lost
        annotations:
          summary: "策略心跳丢失 - {{ $labels.strategy_id }}"
          description: "策略 {{ $labels.strategy_id }} 心跳丢失超过 60 秒"

      # 订单失败率过高
      - alert: HighOrderFailureRate
        expr: |
          (
            rate(strategy_orders_failed_total[5m])
            /
            (rate(strategy_orders_success_total[5m]) + rate(strategy_orders_failed_total[5m]))
          ) > 0.1
        for: 2m
        labels:
          severity: warning
          alert_type: order_failure
        annotations:
          summary: "订单失败率过高 - {{ $labels.strategy_id }}"
          description: "策略 {{ $labels.strategy_id }} 订单失败率超过 10%"

      # 订单延迟过高
      - alert: HighOrderLatency
        expr: |
          histogram_quantile(0.95,
            rate(strategy_order_latency_seconds_bucket[5m])
          ) > 0.1
        for: 5m
        labels:
          severity: warning
          alert_type: high_latency
        annotations:
          summary: "订单延迟过高 - {{ $labels.strategy_id }}"
          description: "策略 {{ $labels.strategy_id }} P95 订单延迟超过 100ms"

      # 策略状态异常
      - alert: StrategyErrorStatus
        expr: strategy_status == -1
        for: 30s
        labels:
          severity: critical
          alert_type: strategy_error
        annotations:
          summary: "策略状态异常 - {{ $labels.strategy_id }}"
          description: "策略 {{ $labels.strategy_id }} 状态为 error"
"""


def generate_alertmanager_rules() -> str:
    """生成 Alertmanager 规则配置"""
    return ALERTMANAGER_RULES_TEMPLATE

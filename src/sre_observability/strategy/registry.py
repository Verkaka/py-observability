"""
Strategy Registry - 策略注册中心

策略启动时自动注册到注册中心，包含：
- 策略元信息 (ID, 名称，团队，负责人)
- 运行状态 (running/stopped/error)
- 指标采集配置
"""
from __future__ import annotations

import json
import logging
import os
import socket
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class StrategyInfo:
    """策略元信息"""
    strategy_id: str
    strategy_name: str
    team: str
    owner: str
    environment: str = "dev"
    version: str = "1.0.0"
    started_at: float = field(default_factory=time.time)
    host: str = field(default_factory=socket.gethostname)
    pid: int = field(default_factory=os.getpid)

    # 运行状态
    status: str = "running"  # running, stopped, error
    last_heartbeat: float = field(default_factory=time.time)

    # 告警配置
    alert_enabled: bool = True
    alert_channels: list = field(default_factory=lambda: ["alert-platform"])

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "team": self.team,
            "owner": self.owner,
            "environment": self.environment,
            "version": self.version,
            "started_at": self.started_at,
            "host": self.host,
            "pid": self.pid,
            "status": self.status,
            "last_heartbeat": self.last_heartbeat,
            "alert_enabled": self.alert_enabled,
            "alert_channels": self.alert_channels,
        }


class StrategyRegistry:
    """
    策略注册中心

    支持两种模式：
    1. 本地模式：策略信息写入本地文件，由 sidecar 进程上报
    2. 远程模式：直接注册到中心化的注册服务 (Redis/数据库)
    """

    def __init__(
        self,
        registry_file: str = "/var/run/strategy-registry.json",
        remote_url: Optional[str] = None,
    ):
        self.registry_file = registry_file
        self.remote_url = remote_url
        self._strategy: Optional[StrategyInfo] = None

    def register(self, strategy: StrategyInfo) -> None:
        """注册策略"""
        self._strategy = strategy

        if self.remote_url:
            self._register_remote(strategy)
        else:
            self._register_local(strategy)

        logger.info(f"Strategy registered: {strategy.strategy_id}")

    def _register_local(self, strategy: StrategyInfo) -> None:
        """本地模式：写入文件"""
        try:
            data = {"strategy": strategy.to_dict(), "timestamp": time.time()}
            with open(self.registry_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to write registry file: {e}")

    def _register_remote(self, strategy: StrategyInfo) -> None:
        """远程模式：HTTP 注册"""
        import urllib.request
        import urllib.error

        try:
            data = json.dumps(strategy.to_dict()).encode()
            req = urllib.request.Request(
                f"{self.remote_url}/register",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                logger.info(f"Remote registry response: {resp.status}")
        except Exception as e:
            logger.warning(f"Failed to register remotely: {e}")

    def heartbeat(self) -> None:
        """发送心跳"""
        if self._strategy:
            self._strategy.last_heartbeat = time.time()
            if self.remote_url:
                self._heartbeat_remote()

    def _heartbeat_remote(self) -> None:
        import urllib.request
        import urllib.error

        try:
            data = json.dumps({
                "strategy_id": self._strategy.strategy_id,
                "last_heartbeat": self._strategy.last_heartbeat,
                "status": self._strategy.status,
            }).encode()
            req = urllib.request.Request(
                f"{self.remote_url}/heartbeat",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            logger.warning(f"Failed to send heartbeat: {e}")

    def unregister(self) -> None:
        """注销策略"""
        if self._strategy:
            self._strategy.status = "stopped"
            if self.remote_url:
                self._unregister_remote()

    def _unregister_remote(self) -> None:
        import urllib.request
        import urllib.error

        try:
            data = json.dumps({"strategy_id": self._strategy.strategy_id}).encode()
            req = urllib.request.Request(
                f"{self.remote_url}/unregister",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            logger.warning(f"Failed to unregister remotely: {e}")


# 全局注册实例
_registry: Optional[StrategyRegistry] = None


def init_registry(
    strategy_id: str,
    strategy_name: str,
    team: str,
    owner: str,
    registry_file: str = "/var/run/strategy-registry.json",
    remote_url: Optional[str] = None,
) -> StrategyRegistry:
    """初始化策略注册"""
    global _registry

    strategy = StrategyInfo(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        team=team,
        owner=owner,
    )

    _registry = StrategyRegistry(registry_file=registry_file, remote_url=remote_url)
    _registry.register(strategy)

    return _registry


def get_registry() -> Optional[StrategyRegistry]:
    """获取全局注册实例"""
    return _registry

"""
Strategy Observability Module

Provides unified observability for quantitative trading strategies:
- Strategy registration
- Business metrics (trades, PnL, positions, latency)
- Alerting integration

Usage:
    from sre_observability.strategy import init_strategy, StrategyContext

    # Initialize
    ctx = init_strategy(
        strategy_id="btc_arb_v1",
        strategy_name="BTC Arbitrage",
        team="quant-team",
        owner="trader@example.com",
    )

    # In trading loop
    with ctx.track_trade("BTCUSDT", "buy", 1.0, 50000):
        execute_trade(...)
"""
from sre_observability.strategy.registry import (
    StrategyInfo,
    StrategyRegistry,
    init_registry,
    get_registry,
)
from sre_observability.strategy.metrics import (
    StrategyMetrics,
    init_strategy_metrics,
    get_strategy_metrics,
)
from sre_observability.strategy.alerts import (
    AlertConfig,
    StrategyAlerter,
    PredefinedAlerts,
    generate_alertmanager_rules,
)

__all__ = [
    # Registry
    "StrategyInfo",
    "StrategyRegistry",
    "init_registry",
    "get_registry",
    # Metrics
    "StrategyMetrics",
    "init_strategy_metrics",
    "get_strategy_metrics",
    # Alerts
    "AlertConfig",
    "StrategyAlerter",
    "PredefinedAlerts",
    "generate_alertmanager_rules",
]

# Convenience
from sre_observability.strategy.context import StrategyContext, init_strategy

__all__ += ["StrategyContext", "init_strategy"]

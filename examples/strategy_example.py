"""
量化策略示例 - 展示如何使用 sre-observability 进行策略监控

运行:
    ENV=prod ALERT_WEBHOOK_URL=http://alert-platform/webhook \
    python examples/strategy_example.py
"""
import random
import time
import signal
import sys

from sre_observability.strategy import init_strategy, setup_observability, ObservabilityConfig


def main():
    # 1. 初始化可观测性 (自动检测 VM/K8s，自动配置 Pushgateway)
    cfg = ObservabilityConfig(
        namespace="quant-team",  # 团队名
        # application 会自动设置为进程名 "strategy_example"
        # environment 会从 ENV 读取
        # pushgateway_url 会根据 environment 自动映射
    )

    # 启动指标采集
    obs = setup_observability(cfg)

    # 2. 初始化策略上下文
    ctx = init_strategy(
        strategy_id="btc_mean_reversion_v1",
        strategy_name="BTC Mean Reversion",
        team="quant-team",
        owner="quant@example.com",
        namespace="quant-team",
        environment="prod",
        version="1.0.0",
        alert_webhook_url="http://alert-platform.internal/webhook",
    )

    # 处理退出信号
    def on_exit(signum, frame):
        print("Shutting down strategy...")
        ctx.stop()
        obs.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    # 3. 策略主循环
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    print("Strategy started, trading...")

    while ctx.is_running:
        symbol = random.choice(symbols)
        side = random.choice(["buy", "sell"])
        volume = random.uniform(0.1, 1.0)
        price = random.uniform(30000, 50000)

        # 4. 交易跟踪 (自动记录延迟、成功率、指标)
        with ctx.track_trade(symbol, side, volume, price):
            # 模拟交易执行
            time.sleep(random.uniform(0.01, 0.05))

            # 随机模拟失败
            if random.random() < 0.05:
                raise Exception("Order rejected")

        # 5. 记录盈亏
        pnl = random.uniform(-100, 150)
        ctx.record_pnl(symbol, pnl)

        # 6. 记录持仓
        position = random.uniform(-5, 5)
        ctx.record_position(symbol, position)

        # 7. 发送心跳 (每 10 秒)
        ctx.heartbeat()

        # 8. 控制循环频率
        time.sleep(1)


if __name__ == "__main__":
    main()

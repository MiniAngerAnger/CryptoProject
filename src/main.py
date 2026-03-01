"""
src/main.py — 采集 + Paper Trading 主程序入口

功能：
- 读取 configs/settings.yaml
- 初始化 SQLite 数据库
- 并发启动 price_feed / onchain_feed
- 启动 trading_loop（baseline / kronos / hybrid）
"""

import sys
import time
import logging
import threading
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# 自动加载 .env 文件（优先于系统环境变量），python-dotenv 可选依赖
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass  # 未安装 python-dotenv 时跳过，依赖 shell 环境变量

from src.storage import db
from src.ingest import price_feed, onchain_feed, sentiment_feed, news_feed
from src.models.kronos_adapter import KronosAdapter, KronosConfig
from src.strategy.signal_engine import SignalEngine
from src.execution.paper_broker import PaperBroker
from src.risk.risk_guard import RiskGuard


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def load_settings() -> dict:
    config_path = PROJECT_ROOT / "configs" / "settings.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_in_thread(target_func, *args, name: str):
    t = threading.Thread(target=target_func, args=args, name=name, daemon=True)
    t.start()
    logger.info(f"✅ 线程启动: {name}")
    return t


def trading_loop(conn, settings: dict):
    tc = settings.get("trading", {})
    if not tc.get("enabled", True):
        logger.info("[trading] 已关闭（trading.enabled=false）")
        return

    symbol = tc.get("symbol", "BTC")
    interval = int(tc.get("interval_seconds", 30))
    lookback = int(tc.get("lookback", 120))

    kronos_cfg_raw = settings.get("kronos", {})
    kronos = KronosAdapter(
        KronosConfig(
            enabled=bool(kronos_cfg_raw.get("enabled", False)),
            lookback=int(kronos_cfg_raw.get("lookback", 240)),
            pred_len=int(kronos_cfg_raw.get("pred_len", 12)),
            model_name=str(kronos_cfg_raw.get("model_name", "NeoQuasar/Kronos-small")),
            tokenizer_name=str(kronos_cfg_raw.get("tokenizer_name", "NeoQuasar/Kronos-Tokenizer-base")),
            max_context=int(kronos_cfg_raw.get("max_context", 512)),
        )
    )

    signal_engine = SignalEngine(settings, kronos=kronos)
    broker = PaperBroker(conn, settings)
    risk = RiskGuard(settings)

    logger.info(
        f"[trading] 启动 | symbol={symbol} interval={interval}s mode={signal_engine.mode} kronos_ready={kronos.ready}"
    )

    while True:
        rows = db.query_prices(conn, symbol=symbol, limit=lookback)
        closes = [float(r["price"]) for r in reversed(rows)]

        if len(closes) < 30:
            db.log_health(conn, "trading", "warmup", f"{symbol} data={len(closes)}")
            time.sleep(interval)
            continue

        last_price = closes[-1]
        sig_raw = signal_engine.generate(closes)
        sentiment = db.query_latest_sentiment(conn)
        sig = signal_engine.apply_sentiment_filter(sig_raw, sentiment)
        qty, _ = broker.get_position(symbol)

        acted = "hold"
        note = sig.reason

        if sig.signal == "buy" and qty <= 0:
            decision = risk.check_entry(broker.cash_usd, last_price)
            if decision.allow:
                ok = broker.buy(symbol, decision.qty, last_price, signal_source=sig.source, note=sig.reason)
                acted = "buy" if ok else "buy_reject"
                if not ok:
                    note = "broker_reject"
            else:
                acted = "risk_block"
                note = decision.reason

        elif sig.signal == "sell" and qty > 0:
            ok = broker.sell_all(symbol, last_price, signal_source=sig.source, note=sig.reason)
            acted = "sell" if ok else "sell_reject"
            if not ok:
                note = "broker_reject"

        broker.mark_equity(symbol, last_price, note=f"sig={sig.signal},act={acted}")
        fg = sentiment["fear_greed_value"] if sentiment else None
        regime = sentiment["regime"] if sentiment else "na"
        news_sc = sentiment["news_score"] if sentiment else None
        db.log_health(
            conn,
            "trading",
            "ok",
            f"{symbol} p={last_price:.2f} sig={sig.signal} src={sig.source} act={acted} "
            f"fg={fg} regime={regime} news={news_sc} cash={broker.cash_usd:.2f}",
        )

        logger.info(
            f"[trading] {symbol} ${last_price:,.2f} sig={sig.signal}/{sig.source} "
            f"act={acted} fg={fg} news={news_sc} cash=${broker.cash_usd:,.2f}"
        )

        time.sleep(interval)


def main():
    logger.info("=" * 50)
    logger.info("🚀 CryptoProject V1.5 采集 + Paper Trading 启动")
    logger.info("=" * 50)

    settings = load_settings()
    logger.info(f"配置加载完成，数据库路径: {settings['database']['path']}")

    conn = db.get_connection(settings["database"]["path"])
    db.init_tables(conn)
    logger.info("数据库表初始化完成")

    run_in_thread(price_feed.run, conn, settings, name="price_feed")
    run_in_thread(onchain_feed.run, conn, settings, name="onchain_feed")
    run_in_thread(news_feed.run, conn, settings, name="news_feed")        # L2：新闻采集
    run_in_thread(sentiment_feed.run, conn, settings, name="sentiment_feed")  # L1+L2：情绪聚合
    run_in_thread(trading_loop, conn, settings, name="trading_loop")

    logger.info("所有模块已启动。按 Ctrl+C 退出。")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\n⏹️  收到中断信号，正在退出...")
        conn.close()
        sys.exit(0)


if __name__ == "__main__":
    main()

"""
src/ingest/price_feed.py — BTC/ETH/SOL/BNB 价格采集器

数据源：CoinGecko 公开 API（国内可访问，一次请求拿全部币种）
每次采集：当前价 + 24h 涨跌幅 + 24h 成交量
频率：由 settings.yaml 的 price_feed.interval_seconds 控制（默认 30s）
"""

import time
import requests
import logging
from src.storage import db

logger = logging.getLogger(__name__)

COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"

# 币种符号 → CoinGecko ID 映射
SYMBOL_TO_ID = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
}


def fetch_prices(symbols: list) -> dict:
    """
    一次请求拿所有币种的价格 + 24h涨跌幅 + 24h成交量。
    返回：{"BTC": {"price": ..., "change_24h": ..., "volume_24h": ...}, ...}
    """
    ids = ",".join(SYMBOL_TO_ID[s] for s in symbols if s in SYMBOL_TO_ID)
    try:
        resp = requests.get(
            COINGECKO_PRICE_URL,
            params={
                "ids": ids,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
            },
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()

        result = {}
        for symbol in symbols:
            cg_id = SYMBOL_TO_ID.get(symbol)
            if cg_id and cg_id in raw:
                d = raw[cg_id]
                result[symbol] = {
                    "price":      d.get("usd", 0),
                    "change_24h": d.get("usd_24h_change", 0),
                    "volume_24h": d.get("usd_24h_vol", 0),
                }
        return result
    except Exception as e:
        logger.error(f"[price_feed] 请求失败: {e}")
        return {}


def run(conn, settings: dict):
    interval = settings["price_feed"]["interval_seconds"]
    symbols  = settings["price_feed"]["symbols"]
    source   = settings["price_feed"]["source"]

    logger.info(f"[price_feed] 启动 | 币种: {symbols} | 间隔: {interval}s")

    while True:
        prices = fetch_prices(symbols)

        if prices:
            for symbol, data in prices.items():
                db.insert_price(
                    conn, symbol,
                    data["price"], data["change_24h"], data["volume_24h"], source
                )
                sign = "▲" if data["change_24h"] >= 0 else "▼"
                logger.info(
                    f"[price_feed] {symbol}: ${data['price']:,.2f} "
                    f"{sign}{abs(data['change_24h']):.2f}%"
                )
            db.log_health(conn, "price_feed", "ok",
                          " | ".join(f"{s}=${d['price']:,.0f}" for s, d in prices.items()))
        else:
            db.log_health(conn, "price_feed", "error", "请求失败，跳过本轮")

        time.sleep(interval)

"""
src/ingest/onchain_feed.py — 链上大额交易监控

核心逻辑迁移自 whale_v2.py：
- 每 5s 轮询 Etherscan，获取最新区块
- 扫描区块内所有交易，过滤出 >= 阈值的 ETH 转账
- 写入 onchain_events 表（tx_hash 唯一，不会重复）
- 大额事件触发 Telegram 推送（可在 settings.yaml 配置阈值）

环境变量：ETHERSCAN_API_KEY（必须）、TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID
"""

import os
import time
import logging
import requests
from src.storage import db
from src.process.normalizer import wei_to_eth, calc_usd_value, get_address_tag
from src.ingest.telegram_notifier import send_whale_alert

logger = logging.getLogger(__name__)

ETHERSCAN_BASE = "https://api.etherscan.io/v2/api"


def get_api_key() -> str:
    key = os.getenv("ETHERSCAN_API_KEY", "")
    if not key:
        logger.warning("[onchain_feed] ETHERSCAN_API_KEY 未设置，将使用公共限速")
    return key


def etherscan_request(params: dict, api_key: str) -> dict | None:
    try:
        base_params = {"chainid": "1", "apikey": api_key}
        base_params.update(params)
        resp = requests.get(ETHERSCAN_BASE, params=base_params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"[onchain_feed] 请求失败: {e}")
        return None


def get_latest_block(api_key: str) -> int | None:
    data = etherscan_request({"module": "proxy", "action": "eth_blockNumber"}, api_key)
    if data and "result" in data:
        try:
            return int(data["result"], 16)
        except ValueError:
            pass
    return None


def get_block_transactions(block_number: int, api_key: str) -> list:
    data = etherscan_request(
        {"module": "proxy", "action": "eth_getBlockByNumber",
         "tag": hex(block_number), "boolean": "true"},
        api_key
    )
    if data and data.get("result"):
        return data["result"].get("transactions", [])
    return []


def get_eth_price_from_db(conn) -> float:
    row = db.query_latest_price(conn, "ETH")
    if row:
        return row["price"]
    return 0.0


def run(conn, settings: dict):
    interval      = settings["onchain_feed"]["interval_seconds"]
    threshold     = settings["onchain_feed"]["whale_threshold_eth"]
    source        = settings["onchain_feed"]["source"]
    address_tags  = settings.get("address_tags", {})

    # Telegram 推送阈值（USD），默认 100 万
    tg_enabled    = settings.get("telegram", {}).get("enabled", False)
    tg_usd_min    = settings.get("telegram", {}).get("threshold_usd", 1_000_000)

    api_key   = get_api_key()
    last_block = 0

    logger.info(f"[onchain_feed] 启动 | 阈值 {threshold} ETH | 轮询 {interval}s | TG推送: {tg_enabled}")

    while True:
        try:
            current_block = get_latest_block(api_key)

            if current_block is None:
                db.log_health(conn, "onchain_feed", "error", "无法获取区块号")
                time.sleep(interval)
                continue

            if current_block <= last_block:
                time.sleep(interval)
                continue

            if last_block == 0:
                last_block = current_block
                logger.info(f"[onchain_feed] 从区块 {current_block:,} 开始监控")
                time.sleep(interval)
                continue

            for block_no in range(last_block + 1, current_block + 1):
                txs       = get_block_transactions(block_no, api_key)
                eth_price = get_eth_price_from_db(conn)

                for tx in txs:
                    raw_value = tx.get("value", "0x0")
                    if raw_value == "0x0":
                        continue

                    amount_eth = wei_to_eth(raw_value)
                    if amount_eth < threshold:
                        continue

                    usd_value = calc_usd_value(amount_eth, eth_price) if eth_price else None
                    from_addr = tx.get("from", "")
                    to_addr   = tx.get("to", "")
                    tx_hash   = tx.get("hash", "")

                    inserted = db.insert_onchain_event(
                        conn, tx_hash, from_addr, to_addr,
                        amount_eth, usd_value, block_no, source
                    )

                    if inserted:
                        from_tag = get_address_tag(from_addr, address_tags)
                        to_tag   = get_address_tag(to_addr, address_tags)
                        usd_str  = f"${usd_value:,.0f}" if usd_value else "?"
                        logger.info(
                            f"🐳 {amount_eth:.2f} ETH ({usd_str}) | "
                            f"{from_tag} → {to_tag} | 区块 {block_no:,}"
                        )

                        # Telegram 推送：满足 USD 阈值才发（避免刷屏）
                        if tg_enabled and usd_value and usd_value >= tg_usd_min:
                            send_whale_alert(amount_eth, usd_value,
                                             from_tag, to_tag, tx_hash, block_no)

            last_block = current_block
            db.log_health(conn, "onchain_feed", "ok", f"已扫描至区块 {current_block:,}")

        except Exception as e:
            logger.error(f"[onchain_feed] 异常: {e}")
            db.log_health(conn, "onchain_feed", "error", str(e))

        time.sleep(interval)

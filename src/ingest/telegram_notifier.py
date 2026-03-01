"""
src/ingest/telegram_notifier.py — Telegram 鲸鱼告警推送

从环境变量读取 BOT_TOKEN 和 CHAT_ID，无硬编码。
onchain_feed 检测到大额事件时调用 send_whale_alert()。
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _get_credentials():
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    return token, chat_id


def send_whale_alert(amount_eth: float, usd_value: float,
                     from_tag: str, to_tag: str,
                     tx_hash: str, block_no: int) -> bool:
    """
    发送鲸鱼告警到 Telegram。
    返回 True = 发送成功，False = 失败或未配置。
    """
    token, chat_id = _get_credentials()
    if not token or not chat_id:
        logger.warning("[telegram] TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 未设置，跳过推送")
        return False

    etherscan_link = f"https://etherscan.io/tx/{tx_hash}"
    usd_str = f"${usd_value:,.0f}" if usd_value else "价格未知"

    # HTML 格式消息，Telegram 支持加粗/链接
    text = (
        f"🐳 <b>鲸鱼警报！</b>\n\n"
        f"💰 <b>{amount_eth:.2f} ETH</b>（{usd_str}）\n"
        f"📤 发送方：{from_tag}\n"
        f"📥 接收方：{to_tag}\n"
        f"📦 区块：{block_no:,}\n"
        f"🔗 <a href='{etherscan_link}'>查看 Etherscan</a>"
    )

    try:
        resp = requests.post(
            TELEGRAM_API.format(token=token),
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        resp.raise_for_status()
        logger.info(f"[telegram] 告警发送成功: {amount_eth:.2f} ETH")
        return True
    except Exception as e:
        logger.error(f"[telegram] 发送失败: {e}")
        return False

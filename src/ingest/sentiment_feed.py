"""L1 消息面采集：Fear & Greed + 预留新闻情绪

- Fear & Greed: alternative.me
- news_score: 当前预留（后续接 NewsAPI/FinBERT）
"""

from __future__ import annotations

import logging
import time
import requests

from src.storage import db

logger = logging.getLogger(__name__)

FNG_URL = "https://api.alternative.me/fng/"


def _fetch_fear_greed() -> tuple[int | None, str]:
    try:
        r = requests.get(FNG_URL, timeout=12)
        r.raise_for_status()
        payload = r.json().get("data", [])
        if not payload:
            return None, "unknown"
        value = int(payload[0].get("value", 0))
        if value <= 25:
            regime = "extreme_fear"
        elif value <= 45:
            regime = "fear"
        elif value <= 55:
            regime = "neutral"
        elif value <= 75:
            regime = "greed"
        else:
            regime = "extreme_greed"
        return value, regime
    except Exception as e:
        logger.warning(f"[sentiment_feed] fear&greed 拉取失败: {e}")
        return None, "unknown"


def _fetch_news_score_placeholder() -> float | None:
    # 预留：后续接 News API + 情绪模型
    return None


def run(conn, settings: dict):
    cfg = settings.get("sentiment", {})
    enabled = bool(cfg.get("enabled", True))
    interval = int(cfg.get("interval_seconds", 300))

    if not enabled:
        logger.info("[sentiment_feed] 已关闭（sentiment.enabled=false）")
        return

    logger.info(f"[sentiment_feed] 启动 | 间隔: {interval}s")

    while True:
        try:
            fg_value, regime = _fetch_fear_greed()
            news_score = _fetch_news_score_placeholder()

            db.insert_sentiment_snapshot(
                conn,
                fear_greed_value=fg_value,
                news_score=news_score,
                regime=regime,
                source="alternative.me+placeholder",
            )
            db.log_health(
                conn,
                "sentiment_feed",
                "ok",
                f"fg={fg_value},regime={regime},news={news_score}",
            )
            logger.info(f"[sentiment_feed] fg={fg_value} regime={regime} news={news_score}")
        except Exception as e:
            db.log_health(conn, "sentiment_feed", "error", str(e))
            logger.warning(f"[sentiment_feed] 异常: {e}")

        time.sleep(interval)

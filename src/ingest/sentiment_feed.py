"""L1+L2 消息面采集：Fear & Greed + 新闻情绪评分

- Fear & Greed: alternative.me（L1）
- news_score: 从 news_events 表聚合最近1小时评分（L2）
  - news_feed 线程负责写入 news_events
  - 本模块只负责聚合并写入 sentiment_snapshots
"""

from __future__ import annotations

import logging
import time
import requests

from src.storage import db
from src.process.sentiment_scoring import aggregate_scores

logger = logging.getLogger(__name__)

FNG_URL = "https://api.alternative.me/fng/"


def _fetch_fear_greed() -> tuple[int | None, str]:
    """拉取 Fear & Greed 指数，失败时降级返回 (None, 'unknown')"""
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
        logger.warning(f"[sentiment_feed] fear&greed 拉取失败（降级）: {e}")
        return None, "unknown"


def _compute_news_score(conn) -> float | None:
    """从 news_events 读取最近1小时评分并聚合为 news_score

    - news_feed 线程负责写入数据，本函数只读
    - 若最近1小时无数据，返回 None（不写入伪零值）
    - 若查询异常，返回 None（降级），不影响 F&G 写入
    """
    try:
        scores = db.query_recent_news_scores(conn, hours=1)
        if not scores:
            return None
        return aggregate_scores(scores)
    except Exception as e:
        logger.warning(f"[sentiment_feed] news_score 计算失败（降级）: {e}")
        return None


def run(conn, settings: dict):
    """情绪采集主循环（独立 daemon 线程）

    每轮：
    1. 拉 Fear & Greed（可独立失败）
    2. 从 DB 聚合 news_score（可独立失败）
    3. 写入 sentiment_snapshots（两者可各自为 None）
    """
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
            news_score = _compute_news_score(conn)

            db.insert_sentiment_snapshot(
                conn,
                fear_greed_value=fg_value,
                news_score=news_score,
                regime=regime,
                source="alternative.me+newsapi",
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

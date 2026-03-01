"""
src/ingest/news_feed.py — L2 新闻源采集（NewsAPI）

职责：
- 通过 NewsAPI everything 接口拉取加密货币相关新闻
- 单次宽泛查询（一次调用覆盖所有目标币种），控制每日 API 消耗
- 对标题做情绪评分，去重（URL UNIQUE），写入 news_events 表
- 写 system_health，异常时自动降级不崩主循环

免费额度说明（newsapi.org developer plan）：
  - 100 requests/day 上限
  - 默认间隔 3600s（1次/小时 = 24次/天），安全使用免费额度
"""

from __future__ import annotations

import logging
import os
import re
import time

import requests

from src.storage import db
from src.process.sentiment_scoring import score_headline

logger = logging.getLogger(__name__)

NEWSAPI_URL = "https://newsapi.org/v2/everything"

# 一次宽泛查询覆盖 BTC/ETH/SOL/BNB，减少 API 调用次数
SEARCH_QUERY = "bitcoin OR ethereum OR solana OR crypto"

# 根据标题关键词推断 symbol（按优先级顺序匹配）
_SYMBOL_KEYWORDS: list[tuple[str, list[str]]] = [
    ("BTC", ["bitcoin", " btc"]),
    ("ETH", ["ethereum", " eth"]),
    ("SOL", ["solana", " sol"]),
    ("BNB", ["binance", " bnb"]),
]


def _detect_symbol(title: str) -> str:
    """从标题关键词推断最相关 symbol，默认 BTC"""
    t = " " + title.lower()  # 前置空格避免匹配 "fetch", "better" 中的 "eth"
    for sym, kws in _SYMBOL_KEYWORDS:
        if any(kw in t for kw in kws):
            return sym
    return "BTC"


def _fetch_articles(api_key: str, page_size: int = 30) -> list[dict]:
    """调用 NewsAPI，返回文章列表；请求失败返回空列表（降级）"""
    try:
        resp = requests.get(
            NEWSAPI_URL,
            params={
                "q": SEARCH_QUERY,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": page_size,
                "apiKey": api_key,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "ok":
            logger.warning(f"[news_feed] NewsAPI 返回异常: {data.get('message')}")
            return []
        return data.get("articles", [])
    except Exception as e:
        logger.warning(f"[news_feed] 请求失败（降级）: {e}")
        return []


def fetch_and_store(conn, api_key: str) -> list[float]:
    """拉取新闻 → 评分 → 去重写库

    Returns:
        本次实际新增条目的评分列表（已存在的跳过不计入）
    """
    if not api_key:
        logger.warning("[news_feed] NEWSAPI_KEY 未配置，跳过采集（降级模式）")
        return []

    articles = _fetch_articles(api_key)
    new_scores: list[float] = []

    for art in articles:
        url = (art.get("url") or "").strip()
        title = (art.get("title") or "").strip()

        # 过滤无效条目（NewsAPI 有时返回 [Removed] 占位标题）
        if not url or not title or title == "[Removed]":
            continue

        source = (art.get("source") or {}).get("name", "") or ""
        published_at = art.get("publishedAt") or ""
        symbol = _detect_symbol(title)
        score = score_headline(title)

        inserted = db.insert_news_event(
            conn,
            symbol=symbol,
            title=title,
            source=source,
            url=url,
            published_at=published_at,
            score=score,
        )
        if inserted:
            new_scores.append(score)

    if new_scores:
        avg = sum(new_scores) / len(new_scores)
        logger.info(f"[news_feed] 新增 {len(new_scores)} 条，avg_score={avg:.3f}")
    else:
        logger.info("[news_feed] 无新增条目（均已存在或 API 返回为空）")

    return new_scores


def run(conn, settings: dict):
    """新闻采集主循环（以独立 daemon 线程运行）

    异常处理：
    - NEWSAPI_KEY 缺失 → 每轮打 warning，跳过，继续 sleep
    - 网络/API 异常 → fetch_and_store 内部已捕获，返回空列表
    - 未预期异常 → 外层 try/except 捕获，写 health error，继续运行
    """
    news_cfg = settings.get("news", {})
    enabled = bool(news_cfg.get("enabled", True))
    interval = int(news_cfg.get("interval_seconds", 3600))

    if not enabled:
        logger.info("[news_feed] 已关闭（news.enabled=false）")
        return

    # 从环境变量读取，不硬编码
    api_key = os.environ.get("NEWSAPI_KEY", "")
    logger.info(f"[news_feed] 启动 | 间隔: {interval}s | api_key_set={bool(api_key)}")

    while True:
        try:
            scores = fetch_and_store(conn, api_key)
            if scores:
                avg = sum(scores) / len(scores)
                status_msg = f"new={len(scores)} avg={avg:.3f}"
            else:
                status_msg = "no_new"
            db.log_health(conn, "news_feed", "ok", status_msg)
        except Exception as e:
            db.log_health(conn, "news_feed", "error", str(e))
            logger.warning(f"[news_feed] 未预期异常: {e}")

        time.sleep(interval)

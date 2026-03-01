"""
src/process/sentiment_scoring.py — 轻量级新闻情绪评分（规则/词典法）

设计原则：
- 不依赖重型 NLP 模型，仅用词典匹配，启动快、无 GPU 依赖
- score_headline: 单条标题打分 → -1.0 到 +1.0
- aggregate_scores: 多条评分聚合 → 综合 news_score
"""

from __future__ import annotations

import re

# ─── 正面词库（看涨/利好/乐观信号）────────────────────────────────────────────
POSITIVE_WORDS: frozenset[str] = frozenset({
    # 价格行情
    "bull", "bullish", "surge", "surges", "surging", "rally", "rallying", "rallied",
    "rise", "rises", "rising", "rose", "gain", "gains", "gained", "higher",
    "record", "breakout", "moon", "pump", "pumped", "pumping", "outperform",
    "uptrend", "ath", "support", "rebound", "bounce",
    # 情绪/态度
    "optimistic", "confident", "positive", "strong", "strengthen", "bullrun",
    # 行业事件（利好）
    "adoption", "approved", "approval", "boost", "recover", "recovery", "recovered",
    "launch", "launches", "launched", "upgrade", "upgrades", "upgraded",
    "expand", "expansion", "invest", "investment", "institutional", "etf",
    "halving", "partnership", "integrate", "integration", "mainstream", "milestone",
    # 资金流向
    "inflow", "inflows", "accumulate", "accumulation", "buy", "buying",
    "profit", "profitable", "growth", "earn",
})

# ─── 负面词库（看跌/利空/悲观信号）────────────────────────────────────────────
NEGATIVE_WORDS: frozenset[str] = frozenset({
    # 价格行情
    "bear", "bearish", "crash", "crashes", "crashed", "fall", "falls", "falling", "fell",
    "drop", "drops", "dropped", "plunge", "plunges", "plunged", "lower",
    "dump", "dumps", "dumped", "sell", "selling", "selloff", "dip", "slump",
    "downtrend", "resistance", "correction",
    # 情绪/态度
    "fear", "worry", "worries", "concerned", "concern", "concerns",
    "panic", "negative", "weak", "uncertainty", "caution", "pessimistic",
    # 监管/法律
    "ban", "banned", "banning", "restrict", "restriction", "restrictions",
    "lawsuit", "sec", "regulation", "regulations", "penalty", "fine",
    "warning", "warnings", "investigate", "investigation", "crackdown",
    "suspend", "suspended", "delist", "delisted", "probe",
    # 安全事件
    "hack", "hacked", "hacking", "exploit", "exploited", "attack",
    "attacks", "phishing", "vulnerability", "rug", "rugpull", "scam", "fraud",
    "fraudulent", "breach",
    # 资金流向
    "outflow", "outflows", "liquidat", "liquidation", "liquidations",
    "loss", "losses", "collapse", "collapses", "collapsed",
    # 宏观风险
    "inflation", "recession",
})


def score_headline(text: str) -> float:
    """对单条新闻标题打分，返回 -1.0 到 +1.0

    算法：
    1. 正则分词并转小写（过滤标点与数字）
    2. 统计命中正面词数量（pos）和负面词数量（neg）
    3. score = (pos - neg) / (pos + neg)
    4. 无命中时返回 0.0（中性）

    Examples:
        "Bitcoin surges to record high"  →  +1.0
        "Bitcoin crashes amid SEC ban"   →  -1.0
        "Bitcoin traded at $95000"       →   0.0
    """
    if not text or not text.strip():
        return 0.0

    # 提取所有纯字母词，转小写（排除数字和标点干扰）
    words = re.findall(r"[a-z]+", text.lower())

    pos_count = sum(1 for w in words if w in POSITIVE_WORDS)
    neg_count = sum(1 for w in words if w in NEGATIVE_WORDS)

    total = pos_count + neg_count
    if total == 0:
        return 0.0

    # 线性归一化到 [-1, +1]
    return (pos_count - neg_count) / total


def aggregate_scores(scores: list[float]) -> float:
    """将多条新闻评分聚合为单一 news_score（简单算术均值）

    Args:
        scores: 单条标题评分列表，每项 -1.0 ~ +1.0

    Returns:
        float: 聚合后的综合情绪分，空列表返回 0.0
    """
    if not scores:
        return 0.0
    return sum(scores) / len(scores)

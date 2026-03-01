"""交易信号引擎（baseline + kronos + hybrid）"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Literal

from src.models.kronos_adapter import KronosAdapter

Signal = Literal["buy", "sell", "hold"]


@dataclass
class SignalResult:
    signal: Signal
    reason: str
    source: str


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    if len(values) < period:
        return float(mean(values))
    k = 2 / (period + 1)
    ema_val = float(values[0])
    for v in values[1:]:
        ema_val = v * k + ema_val * (1 - k)
    return ema_val


class SignalEngine:
    def __init__(self, settings: dict, kronos: KronosAdapter | None = None):
        strat = settings.get("strategy", {})
        sent = settings.get("sentiment", {})
        self.mode = strat.get("mode", "baseline")  # baseline | kronos | hybrid
        self.fast = int(strat.get("ema_fast", 9))
        self.slow = int(strat.get("ema_slow", 21))
        self.kronos_threshold = float(strat.get("kronos_threshold", 0.003))  # 0.3%
        self.block_greed_above = int(sent.get("fear_greed_block_greed_above", 75))
        # news_score 低于此阈值时 buy 降级为 hold（-0.3 默认允许轻度负面情绪）
        self.min_news_score = float(sent.get("min_news_score", -0.3))
        self.kronos = kronos

    def _baseline_signal(self, closes: list[float]) -> SignalResult:
        if len(closes) < max(self.fast, self.slow) + 2:
            return SignalResult("hold", "insufficient_data", "baseline")

        fast_now = _ema(closes[-self.fast * 3 :], self.fast)
        slow_now = _ema(closes[-self.slow * 3 :], self.slow)

        if fast_now > slow_now:
            return SignalResult("buy", f"ema{self.fast}>{self.slow}", "baseline")
        if fast_now < slow_now:
            return SignalResult("sell", f"ema{self.fast}<{self.slow}", "baseline")
        return SignalResult("hold", "ema_flat", "baseline")

    def generate(self, closes: list[float]) -> SignalResult:
        base = self._baseline_signal(closes)

        if self.mode == "baseline" or not self.kronos:
            return base

        delta = self.kronos.predict_close_delta(closes)
        if delta is None:
            # kronos 不可用时自动降级
            return base

        if self.mode == "kronos":
            if delta >= self.kronos_threshold:
                return SignalResult("buy", f"kronos_delta={delta:.4f}", "kronos")
            if delta <= -self.kronos_threshold:
                return SignalResult("sell", f"kronos_delta={delta:.4f}", "kronos")
            return SignalResult("hold", f"kronos_delta={delta:.4f}", "kronos")

        # hybrid: baseline 与 kronos 同向才执行，否则 hold
        k_signal: Signal = "hold"
        if delta >= self.kronos_threshold:
            k_signal = "buy"
        elif delta <= -self.kronos_threshold:
            k_signal = "sell"

        if base.signal == k_signal and k_signal != "hold":
            return SignalResult(k_signal, f"hybrid_ok base={base.reason},delta={delta:.4f}", "hybrid")

        return SignalResult("hold", f"hybrid_block base={base.signal},k={k_signal},delta={delta:.4f}", "hybrid")

    def apply_sentiment_filter(self, signal: SignalResult, sentiment_row) -> SignalResult:
        """消息面过滤（L1 + L2）：

        过滤顺序（仅对 buy 信号生效，sell 不拦截）：
        1. extreme_greed（F&G > block_greed_above）→ hold（避免高位接盘）
        2. news_score < min_news_score           → hold（新闻情绪过差时不买）
        3. extreme_fear                          → 保留 buy（反向机会，交风控决定仓位）
        """
        if not sentiment_row:
            return signal

        if signal.signal != "buy":
            # sell 信号直接放行，不受情绪限制
            return signal

        fg = sentiment_row["fear_greed_value"]
        regime = (sentiment_row["regime"] or "").lower()
        news_score = sentiment_row["news_score"]

        # L1 过滤：极度贪婪时不买
        if regime == "extreme_greed" or (fg is not None and int(fg) >= self.block_greed_above):
            return SignalResult("hold", f"sentiment_block_greed fg={fg}", "sentiment_filter")

        # L2 过滤：新闻情绪低于阈值时不买
        if news_score is not None and news_score < self.min_news_score:
            return SignalResult(
                "hold",
                f"news_filter score={news_score:.3f}<{self.min_news_score}",
                "sentiment_filter",
            )

        # 极度恐惧：保留 buy（反向机会）
        if regime == "extreme_fear":
            return SignalResult("buy", f"sentiment_allow_fear fg={fg}", signal.source)

        return signal

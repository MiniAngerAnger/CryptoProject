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
        self.mode = strat.get("mode", "baseline")  # baseline | kronos | hybrid
        self.fast = int(strat.get("ema_fast", 9))
        self.slow = int(strat.get("ema_slow", 21))
        self.kronos_threshold = float(strat.get("kronos_threshold", 0.003))  # 0.3%
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

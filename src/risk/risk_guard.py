"""基础风控守卫（paper trading）"""

from dataclasses import dataclass


@dataclass
class RiskDecision:
    allow: bool
    reason: str
    qty: float = 0.0


class RiskGuard:
    def __init__(self, settings: dict):
        cfg = settings.get("risk", {})
        self.max_notional_pct = float(cfg.get("max_notional_pct", 0.2))
        self.min_trade_usd = float(cfg.get("min_trade_usd", 50))

    def check_entry(self, cash_usd: float, price: float) -> RiskDecision:
        if price <= 0:
            return RiskDecision(False, "invalid_price", 0.0)

        budget = cash_usd * self.max_notional_pct
        if budget < self.min_trade_usd:
            return RiskDecision(False, "budget_too_small", 0.0)

        qty = budget / price
        if qty <= 0:
            return RiskDecision(False, "qty_zero", 0.0)

        return RiskDecision(True, "ok", qty)

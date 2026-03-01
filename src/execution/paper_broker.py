"""Paper Broker：模拟成交与仓位管理"""

from __future__ import annotations

from dataclasses import dataclass

from src.storage import db


@dataclass
class BrokerState:
    cash_usd: float
    symbol: str
    qty: float
    avg_price: float


class PaperBroker:
    def __init__(self, conn, settings: dict):
        paper_cfg = settings.get("paper_trading", {})
        self.conn = conn
        self.fee_bps = float(paper_cfg.get("fee_bps", 10))  # 0.10%
        self.slippage_bps = float(paper_cfg.get("slippage_bps", 5))  # 0.05%
        self.cash_usd = float(paper_cfg.get("initial_balance_usd", 10000))

        latest_eq = db.query_latest_equity(conn)
        if latest_eq:
            self.cash_usd = float(latest_eq["balance_usd"])

    def _fee(self, notional: float) -> float:
        return notional * self.fee_bps / 10000.0

    def _slip_price(self, price: float, side: str) -> float:
        s = self.slippage_bps / 10000.0
        if side == "buy":
            return price * (1 + s)
        return price * (1 - s)

    def get_position(self, symbol: str) -> tuple[float, float]:
        pos = db.query_position(self.conn, symbol)
        if not pos:
            return 0.0, 0.0
        return float(pos["qty"]), float(pos["avg_price"])

    def mark_equity(self, symbol: str, mark_price: float, note: str = ""):
        qty, _ = self.get_position(symbol)
        db.insert_equity(self.conn, self.cash_usd, qty * mark_price, note=note)

    def buy(self, symbol: str, qty: float, price: float, signal_source: str, note: str = "") -> bool:
        if qty <= 0 or price <= 0:
            return False
        fill_price = self._slip_price(price, "buy")
        notional = qty * fill_price
        fee = self._fee(notional)
        cost = notional + fee
        if self.cash_usd < cost:
            return False

        cur_qty, cur_avg = self.get_position(symbol)
        new_qty = cur_qty + qty
        new_avg = ((cur_qty * cur_avg) + (qty * fill_price)) / new_qty if new_qty > 0 else 0.0

        self.cash_usd -= cost

        order_id = db.create_order(self.conn, symbol, "buy", qty, signal_source=signal_source, note=note)
        db.create_fill(self.conn, order_id, symbol, "buy", qty, fill_price, fee)
        db.upsert_position(self.conn, symbol, new_qty, new_avg)
        return True

    def sell_all(self, symbol: str, price: float, signal_source: str, note: str = "") -> bool:
        qty, _ = self.get_position(symbol)
        if qty <= 0 or price <= 0:
            return False

        fill_price = self._slip_price(price, "sell")
        notional = qty * fill_price
        fee = self._fee(notional)
        proceeds = notional - fee

        self.cash_usd += proceeds

        order_id = db.create_order(self.conn, symbol, "sell", qty, signal_source=signal_source, note=note)
        db.create_fill(self.conn, order_id, symbol, "sell", qty, fill_price, fee)
        db.upsert_position(self.conn, symbol, 0.0, 0.0)
        return True

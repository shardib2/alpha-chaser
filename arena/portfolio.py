"""Paper-portfolio accounting: long-only, whole shares, cash-constrained."""

from dataclasses import dataclass, field


@dataclass
class Position:
    shares: int
    avg_cost: float

    def to_dict(self) -> dict:
        return {"shares": self.shares, "avg_cost": round(self.avg_cost, 4)}


@dataclass
class Portfolio:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0

    def buy(self, ticker: str, quantity: int, price: float) -> int:
        """Buy up to `quantity` shares, clamped by available cash. Returns shares filled."""
        if price <= 0 or quantity <= 0:
            return 0
        affordable = int(self.cash // price)
        filled = min(quantity, affordable)
        if filled <= 0:
            return 0
        cost = filled * price
        pos = self.positions.get(ticker)
        if pos:
            total_cost = pos.avg_cost * pos.shares + cost
            pos.shares += filled
            pos.avg_cost = total_cost / pos.shares
        else:
            self.positions[ticker] = Position(shares=filled, avg_cost=price)
        self.cash -= cost
        return filled

    def sell(self, ticker: str, quantity: int, price: float) -> int:
        """Sell up to `quantity` shares, clamped by holdings. Returns shares filled."""
        pos = self.positions.get(ticker)
        if not pos or price <= 0 or quantity <= 0:
            return 0
        filled = min(quantity, pos.shares)
        self.cash += filled * price
        self.realized_pnl += filled * (price - pos.avg_cost)
        pos.shares -= filled
        if pos.shares == 0:
            del self.positions[ticker]
        return filled

    def equity(self, prices: dict[str, float]) -> float:
        value = self.cash
        for ticker, pos in self.positions.items():
            value += pos.shares * prices.get(ticker, pos.avg_cost)
        return value

    def to_dict(self) -> dict:
        return {
            "cash": round(self.cash, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "positions": {t: p.to_dict() for t, p in sorted(self.positions.items())},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Portfolio":
        return cls(
            cash=d["cash"],
            realized_pnl=d.get("realized_pnl", 0.0),
            positions={t: Position(**p) for t, p in d.get("positions", {}).items()},
        )

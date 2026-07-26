from arena.portfolio import Portfolio


def test_buy_clamps_to_cash():
    p = Portfolio(cash=1000.0)
    filled = p.buy("AAPL", 100, 100.0)
    assert filled == 10
    assert p.cash == 0.0
    assert p.positions["AAPL"].shares == 10


def test_sell_clamps_to_holdings_and_realizes_pnl():
    p = Portfolio(cash=0.0)
    p.positions["AAPL"] = __import__("arena.portfolio", fromlist=["Position"]).Position(shares=5, avg_cost=100.0)
    filled = p.sell("AAPL", 50, 110.0)
    assert filled == 5
    assert p.cash == 550.0
    assert round(p.realized_pnl, 2) == 50.0
    assert "AAPL" not in p.positions


def test_sell_without_position_fills_nothing():
    p = Portfolio(cash=100.0)
    assert p.sell("TSLA", 10, 300.0) == 0
    assert p.cash == 100.0


def test_avg_cost_blends_on_repeat_buys():
    p = Portfolio(cash=10000.0)
    p.buy("MSFT", 10, 100.0)
    p.buy("MSFT", 10, 200.0)
    assert p.positions["MSFT"].shares == 20
    assert p.positions["MSFT"].avg_cost == 150.0


def test_equity_uses_market_prices():
    p = Portfolio(cash=500.0)
    p.buy("NVDA", 2, 100.0)
    assert p.equity({"NVDA": 150.0}) == 300.0 + 2 * 150.0


def test_round_trip_serialization():
    p = Portfolio(cash=123.45)
    p.buy("KO", 3, 40.0)
    restored = Portfolio.from_dict(p.to_dict())
    assert restored.cash == p.to_dict()["cash"]
    assert restored.positions["KO"].shares == 3

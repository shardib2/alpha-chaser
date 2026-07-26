"""The arena cycle: give every LLM the same market snapshot, let each trade its own book.

One cycle = one API call per competitor. Decisions are validated and clamped
(long-only, whole shares, cash-limited, position-size cap), executed at the
latest price, and everything is persisted to data/state.json + data/trades.jsonl.
"""

import json
import logging
from datetime import date
from pathlib import Path

from .config import ArenaConfig, Competitor
from .market_data import MarketData
from .portfolio import Portfolio

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STATE_PATH = DATA_DIR / "state.json"
TRADES_PATH = DATA_DIR / "trades.jsonl"

SYSTEM_PROMPT = """You are {display}, an autonomous portfolio manager competing in a public trading arena \
against other AI models. Every competitor started with the same cash; you are ranked publicly on total return.

YOUR STRATEGY MANDATE (stick to it — it is what makes you different from the other models):
{strategy}

Rules:
- Long-only, whole shares, no leverage. You can only spend the cash you have.
- At most {max_orders} orders this cycle. No single position may exceed {max_pos_pct:.0f}% of your equity.
- You may hold cash — trading every cycle is not required. "orders": [] is a valid answer.
- Respond with ONLY a JSON object, no other text, in exactly this shape:
{{"market_view": "<1-2 sentence read of the market>",
  "orders": [{{"action": "buy"|"sell", "ticker": "TICKER", "quantity": <positive integer>, "reasoning": "<1 sentence>"}}]}}"""


def _load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"cycles_run": 0, "created": None, "portfolios": {}, "benchmark": {}, "usage": {}}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def _append_trades(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def build_user_prompt(today: str, comp_state: dict, snapshot: dict, recent_trades: list[dict]) -> str:
    """The full context each model sees, as one JSON blob (easy to parse, easy to log)."""
    return json.dumps(
        {
            "date": today,
            "your_portfolio": comp_state,
            "market_snapshot": snapshot,
            "your_recent_trades": recent_trades[-15:],
            "instructions": "Analyze the snapshot through the lens of your strategy mandate, then return your JSON decision.",
        },
        indent=1,
    )


def _portfolio_context(portfolio: Portfolio, prices: dict[str, float], starting_cash: float) -> dict:
    equity = portfolio.equity(prices)
    positions = {}
    for t, p in portfolio.positions.items():
        px = prices.get(t, p.avg_cost)
        positions[t] = {
            "shares": p.shares,
            "avg_cost": round(p.avg_cost, 2),
            "price": round(px, 2),
            "value": round(p.shares * px, 2),
            "unrealized_pnl_pct": round((px / p.avg_cost - 1) * 100, 2) if p.avg_cost else 0.0,
        }
    return {
        "cash": round(portfolio.cash, 2),
        "equity": round(equity, 2),
        "total_return_pct": round((equity / starting_cash - 1) * 100, 2),
        "positions": positions,
    }


def _validate_and_execute(
    comp: Competitor,
    decision: dict,
    portfolio: Portfolio,
    market: MarketData,
    config: ArenaConfig,
    today: str,
) -> list[dict]:
    """Apply a model's orders with hard guardrails. Returns trade-log records."""
    records = []
    orders = decision.get("orders") or []
    if not isinstance(orders, list):
        orders = []
    for order in orders[: config.max_orders_per_cycle]:
        rec = {
            "date": today,
            "competitor": comp.id,
            "model": comp.model,
            "order": order,
            "status": "rejected",
            "filled": 0,
            "fill_price": None,
        }
        try:
            action = str(order.get("action", "")).lower()
            ticker = str(order.get("ticker", "")).upper().strip()
            quantity = int(order.get("quantity", 0))
        except (TypeError, ValueError):
            rec["reason"] = "malformed order"
            records.append(rec)
            continue
        if action not in ("buy", "sell") or not ticker or quantity <= 0:
            rec["reason"] = "invalid action/ticker/quantity"
            records.append(rec)
            continue
        quote = market.get(ticker)
        if quote is None:
            rec["reason"] = f"no price available for {ticker}"
            records.append(rec)
            continue
        price = quote.price

        if action == "buy":
            prices_now = {t: (market.get(t).price if market.get(t) else p.avg_cost)
                          for t, p in portfolio.positions.items()}
            equity = portfolio.equity(prices_now)
            held_value = portfolio.positions.get(ticker)
            held_value = held_value.shares * price if held_value else 0.0
            max_additional = config.max_position_pct * equity - held_value
            cap_by_position = max(0, int(max_additional // price))
            quantity = min(quantity, cap_by_position)
            if quantity <= 0:
                rec["reason"] = f"position cap {config.max_position_pct:.0%} of equity reached"
                records.append(rec)
                continue
            filled = portfolio.buy(ticker, quantity, price)
        else:
            filled = portfolio.sell(ticker, quantity, price)

        if filled > 0:
            rec["status"] = "filled" if filled == int(order.get("quantity", 0)) else "partial"
            rec["filled"] = filled
            rec["fill_price"] = round(price, 2)
        else:
            rec["reason"] = "insufficient cash" if action == "buy" else "no shares held"
        records.append(rec)
    return records


def run_cycle(
    config: ArenaConfig,
    llm_client,
    market: MarketData,
    state_path: Path = STATE_PATH,
    trades_path: Path = TRADES_PATH,
    today: str | None = None,
) -> dict:
    """Run one full arena cycle. Returns a summary dict for logging/CI output."""
    today = today or date.today().isoformat()
    state = _load_state(state_path)
    state["created"] = state["created"] or today

    snapshot = market.snapshot(config.universe)
    if len(snapshot) < max(3, len(config.universe) // 4):
        raise RuntimeError(
            f"market data too sparse ({len(snapshot)}/{len(config.universe)} tickers); refusing to trade blind"
        )

    bench_quote = market.get(config.benchmark)
    if bench_quote:
        bench = state["benchmark"]
        bench.setdefault("start_price", bench_quote.price)
        bench.setdefault("history", []).append({"date": today, "price": round(bench_quote.price, 2)})

    prior_trades = []
    if trades_path.exists():
        prior_trades = [json.loads(line) for line in trades_path.read_text().splitlines() if line.strip()]

    summary = {"date": today, "results": {}}
    new_records = []
    for comp in config.competitors:
        pstate = state["portfolios"].get(comp.id)
        portfolio = Portfolio.from_dict(pstate["book"]) if pstate else Portfolio(cash=config.starting_cash)

        prices = {t: q["price"] for t, q in snapshot.items()}
        ctx = _portfolio_context(portfolio, prices, config.starting_cash)
        my_trades = [
            {"date": r["date"], **r["order"], "status": r["status"]}
            for r in prior_trades
            if r.get("competitor") == comp.id
        ]
        user_prompt = build_user_prompt(today, ctx, snapshot, my_trades)
        system_prompt = SYSTEM_PROMPT.format(
            display=comp.display,
            strategy=comp.strategy,
            max_orders=config.max_orders_per_cycle,
            max_pos_pct=config.max_position_pct * 100,
        )

        try:
            decision, usage = llm_client.decide(comp.model, system_prompt, user_prompt)
        except Exception as e:  # noqa: BLE001 - one model failing must not kill the arena
            log.error("%s (%s) failed to decide: %s", comp.display, comp.model, e)
            summary["results"][comp.id] = {"error": str(e)}
            decision, usage = {"orders": [], "market_view": f"ERROR: {e}"}, {}

        records = _validate_and_execute(comp, decision, portfolio, market, config, today)
        new_records.extend(records)

        u = state["usage"].setdefault(comp.id, {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0})
        u["prompt_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
        u["completion_tokens"] += int(usage.get("completion_tokens", 0) or 0)
        u["calls"] += 1

        equity = portfolio.equity(prices)
        history = (pstate or {}).get("history", [])
        history.append({"date": today, "equity": round(equity, 2)})
        state["portfolios"][comp.id] = {
            "display": comp.display,
            "model": comp.model,
            "book": portfolio.to_dict(),
            "history": history,
            "last_market_view": str(decision.get("market_view", ""))[:500],
        }
        summary["results"].setdefault(comp.id, {})
        summary["results"][comp.id].update(
            {
                "equity": round(equity, 2),
                "return_pct": round((equity / config.starting_cash - 1) * 100, 2),
                "orders_submitted": len(decision.get("orders") or []),
                "orders_filled": sum(1 for r in records if r["status"] in ("filled", "partial")),
            }
        )

    state["cycles_run"] += 1
    _save_state(state_path, state)
    _append_trades(trades_path, new_records)
    return summary

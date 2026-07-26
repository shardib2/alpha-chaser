"""Render the public leaderboard (LEADERBOARD.md) from data/state.json."""

import json
from pathlib import Path

from .engine import STATE_PATH

LEADERBOARD_PATH = Path(__file__).resolve().parent.parent / "LEADERBOARD.md"


def _benchmark_return(state: dict) -> float | None:
    bench = state.get("benchmark", {})
    hist = bench.get("history") or []
    start = bench.get("start_price")
    if not start or not hist:
        return None
    return (hist[-1]["price"] / start - 1) * 100


def render(state: dict, starting_cash: float) -> str:
    rows = []
    for comp_id, p in state.get("portfolios", {}).items():
        hist = p.get("history") or []
        equity = hist[-1]["equity"] if hist else starting_cash
        ret = (equity / starting_cash - 1) * 100
        book = p.get("book", {})
        positions = book.get("positions", {})
        top = sorted(positions.items(), key=lambda kv: -kv[1]["shares"] * kv[1]["avg_cost"])[:3]
        top_str = ", ".join(t for t, _ in top) if top else "(all cash)"
        rows.append(
            {
                "id": comp_id,
                "display": p.get("display", comp_id),
                "model": p.get("model", "?"),
                "equity": equity,
                "ret": ret,
                "cash": book.get("cash", 0.0),
                "n_pos": len(positions),
                "top": top_str,
                "view": p.get("last_market_view", ""),
            }
        )
    rows.sort(key=lambda r: -r["ret"])

    bench_ret = _benchmark_return(state)
    as_of = None
    for p in state.get("portfolios", {}).values():
        if p.get("history"):
            as_of = p["history"][-1]["date"]
            break

    lines = [
        "# LLM Trading Arena — Leaderboard",
        "",
        f"**As of:** {as_of or 'never run'} &nbsp;|&nbsp; **Cycles:** {state.get('cycles_run', 0)}"
        + (f" &nbsp;|&nbsp; **SPY benchmark:** {bench_ret:+.2f}%" if bench_ret is not None else ""),
        "",
        "| # | Model | Return | Equity | vs SPY | Cash | Positions | Top holdings |",
        "|---|-------|-------:|-------:|-------:|-----:|----------:|--------------|",
    ]
    for i, r in enumerate(rows, 1):
        vs = f"{r['ret'] - bench_ret:+.2f}%" if bench_ret is not None else "—"
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, str(i))
        lines.append(
            f"| {medal} | **{r['display']}** (`{r['model']}`) | {r['ret']:+.2f}% | "
            f"${r['equity']:,.0f} | {vs} | ${r['cash']:,.0f} | {r['n_pos']} | {r['top']} |"
        )
    lines += ["", "## Latest market views", ""]
    for r in rows:
        if r["view"]:
            lines.append(f"- **{r['display']}**: {r['view']}")
    lines += [
        "",
        "_Paper trading. Every order, fill, and rejection is logged in `data/trades.jsonl`;_",
        "_full portfolio state and equity history in `data/state.json`._",
        "",
    ]
    return "\n".join(lines)


def write(state_path: Path = STATE_PATH, out_path: Path = LEADERBOARD_PATH, starting_cash: float = 100000.0) -> str:
    state = json.loads(Path(state_path).read_text())
    md = render(state, starting_cash)
    out_path.write_text(md)
    return md

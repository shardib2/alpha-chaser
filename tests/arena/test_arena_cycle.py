"""End-to-end offline test: two full cycles with fixture prices and a fake LLM."""

import json
from pathlib import Path

from arena import leaderboard
from arena.config import ArenaConfig
from arena.engine import run_cycle
from arena.llm import FakeLLM
from arena.market_data import FixtureMarketData

FIXTURES = Path(__file__).parent / "fixtures" / "prices.json"
CONFIG = Path(__file__).parent.parent.parent / "arena_config.json"


def _run(tmp_path, today):
    config = ArenaConfig.load(CONFIG)
    market = FixtureMarketData(json.loads(FIXTURES.read_text()))
    return (
        run_cycle(
            config,
            FakeLLM(),
            market,
            state_path=tmp_path / "state.json",
            trades_path=tmp_path / "trades.jsonl",
            today=today,
        ),
        config,
    )


def test_two_cycles_end_to_end(tmp_path):
    summary1, config = _run(tmp_path, "2026-07-24")
    assert set(summary1["results"].keys()) == {c.id for c in config.competitors}
    # every competitor made a decision without error and at least one trade filled
    assert not any("error" in r for r in summary1["results"].values())
    assert any(r["orders_filled"] > 0 for r in summary1["results"].values())

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["cycles_run"] == 1
    for comp in config.competitors:
        book = state["portfolios"][comp.id]["book"]
        # cash never negative, equity accounted
        assert book["cash"] >= 0
        assert state["portfolios"][comp.id]["history"][-1]["equity"] > 0

    summary2, _ = _run(tmp_path, "2026-07-25")
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["cycles_run"] == 2
    assert len(state["portfolios"][config.competitors[0].id]["history"]) == 2

    # trade log is append-only jsonl with valid records
    lines = (tmp_path / "trades.jsonl").read_text().splitlines()
    assert lines
    for line in lines:
        rec = json.loads(line)
        assert rec["status"] in ("filled", "partial", "rejected")

    # leaderboard renders
    md = leaderboard.render(state, config.starting_cash)
    assert "Leaderboard" in md
    for comp in config.competitors:
        assert comp.display in md


def test_failing_model_does_not_kill_cycle(tmp_path):
    class ExplodingLLM(FakeLLM):
        def decide(self, model, system_prompt, user_prompt):
            if "gpt" in model:
                raise RuntimeError("simulated provider outage")
            return super().decide(model, system_prompt, user_prompt)

    config = ArenaConfig.load(CONFIG)
    market = FixtureMarketData(json.loads(FIXTURES.read_text()))
    summary = run_cycle(
        config,
        ExplodingLLM(),
        market,
        state_path=tmp_path / "state.json",
        trades_path=tmp_path / "trades.jsonl",
        today="2026-07-24",
    )
    assert "error" in summary["results"]["gpt"]
    # the failed model still has a portfolio (all cash) and everyone else traded
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["portfolios"]["gpt"]["book"]["cash"] == config.starting_cash
    others = [r for cid, r in summary["results"].items() if cid != "gpt"]
    assert any(r.get("orders_filled", 0) > 0 for r in others)


def test_position_cap_enforced(tmp_path):
    class AllInLLM(FakeLLM):
        def decide(self, model, system_prompt, user_prompt):
            return (
                {"orders": [{"action": "buy", "ticker": "AAPL", "quantity": 100000,
                             "reasoning": "all in"}], "market_view": "yolo"},
                {},
            )

    config = ArenaConfig.load(CONFIG)
    market = FixtureMarketData(json.loads(FIXTURES.read_text()))
    run_cycle(
        config,
        AllInLLM(),
        market,
        state_path=tmp_path / "state.json",
        trades_path=tmp_path / "trades.jsonl",
        today="2026-07-24",
    )
    state = json.loads((tmp_path / "state.json").read_text())
    for comp in config.competitors:
        book = state["portfolios"][comp.id]["book"]
        pos = book["positions"].get("AAPL")
        assert pos is not None
        aapl_price = json.loads(FIXTURES.read_text())["AAPL"][-1]
        equity = state["portfolios"][comp.id]["history"][-1]["equity"]
        assert pos["shares"] * aapl_price <= config.max_position_pct * equity * 1.01

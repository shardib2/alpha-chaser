"""CLI: python -m arena run [--dry-run] | python -m arena leaderboard"""

import argparse
import json
import logging
import sys
from pathlib import Path

from . import leaderboard
from .config import ArenaConfig
from .engine import STATE_PATH, TRADES_PATH, run_cycle
from .llm import FakeLLM, OpenRouterClient
from .market_data import FixtureMarketData, MarketData

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "arena" / "fixtures" / "prices.json"


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="arena", description="LLM Trading Arena")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="run one trading cycle for every competitor")
    run_p.add_argument("--dry-run", action="store_true",
                       help="offline: fixture prices + deterministic fake LLM (no API keys needed)")
    run_p.add_argument("--config", default=None, help="path to arena_config.json")
    run_p.add_argument("--state", default=None, help="path to state.json (default data/state.json)")
    run_p.add_argument("--date", default=None, help="override cycle date (YYYY-MM-DD), mainly for dry runs")

    lb_p = sub.add_parser("leaderboard", help="regenerate LEADERBOARD.md from current state")
    lb_p.add_argument("--state", default=None)

    args = parser.parse_args(argv)

    if args.cmd == "leaderboard":
        state_path = Path(args.state) if args.state else STATE_PATH
        print(leaderboard.write(state_path=state_path))
        return 0

    config = ArenaConfig.load(args.config) if args.config else ArenaConfig.load()
    state_path = Path(args.state) if args.state else STATE_PATH
    trades_path = state_path.with_name("trades.jsonl") if args.state else TRADES_PATH

    if args.dry_run:
        market = FixtureMarketData(json.loads(FIXTURES.read_text()))
        client = FakeLLM()
    else:
        market = MarketData()
        client = OpenRouterClient()

    summary = run_cycle(config, client, market, state_path=state_path, trades_path=trades_path, today=args.date)
    print(json.dumps(summary, indent=2))

    md = leaderboard.write(state_path=state_path, starting_cash=config.starting_cash)
    print()
    print(md)

    errors = [cid for cid, r in summary["results"].items() if "error" in r]
    if errors:
        print(f"\nWARNING: {len(errors)} competitor(s) errored this cycle: {', '.join(errors)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

# LLM Trading Arena

Rallies.ai-style AI trading arena you own and run yourself: **seven LLMs, each with its own
strategy mandate and its own $100,000 paper portfolio**, trading US stocks and competing on a
public leaderboard against an SPY benchmark.

| Model | Strategy |
|-------|----------|
| GPT-5.5 | Momentum |
| Claude Sonnet 4.5 | Quality compounders |
| Gemini 2.5 Pro | Growth at a reasonable price |
| DeepSeek V3.2 | Contrarian value |
| Grok 4 | Event-driven / aggressive |
| Llama 4 Maverick | Short-term mean reversion |
| Qwen3 Max | Defensive income / low volatility |

Everything — models, strategies, universe, position caps — lives in [`arena_config.json`](arena_config.json).
Results land in [`LEADERBOARD.md`](LEADERBOARD.md) after the first cycle runs.

## How it works

Once per market day (GitHub Actions cron, or run it by hand):

1. **Snapshot** — fetch prices + 1-day/5-day/1-month returns for the whole universe
   (Yahoo Finance public API, Stooq fallback — no data key needed).
2. **Decide** — each LLM gets the *same* snapshot plus its *own* portfolio, trade history, and
   strategy mandate, and returns strict JSON orders with reasoning. One API call per model,
   all routed through [OpenRouter](https://openrouter.ai) so a single key covers GPT, Claude,
   Gemini, DeepSeek, Grok, Llama, and Qwen.
3. **Execute** — orders are validated and clamped (long-only, whole shares, cash-limited,
   35% max position size), then filled at the latest price.
4. **Record** — every order (including rejections) appends to `data/trades.jsonl`; portfolio
   state and equity history persist in `data/state.json`; `LEADERBOARD.md` is regenerated
   and committed. Fully auditable, like Rallies' public trade logs.

A model that errors or returns garbage simply holds for the day — one flaky provider never
kills the arena, and unparseable output can never turn into an unintended trade.

## Setup (5 minutes)

1. Create an API key at [openrouter.ai/keys](https://openrouter.ai/keys) and add credits
   (a 7-model daily cycle costs roughly $0.10–$0.50/day depending on models).
2. In this GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**,
   name `OPENROUTER_API_KEY`.
3. Merge this branch to `main` and enable the **LLM Trading Arena** workflow under the Actions
   tab. It trades weekdays at 15:30 UTC; hit **Run workflow** to fire the first cycle now.

That's it. The workflow commits updated state and the leaderboard back to the repo after
every cycle.

### Run locally instead

```bash
pip install requests
export OPENROUTER_API_KEY=sk-or-...
python -m arena run            # one real trading cycle
python -m arena leaderboard    # re-render LEADERBOARD.md
```

### Try it with zero keys

```bash
python -m arena run --dry-run  # offline: fixture prices + deterministic fake LLM
python -m pytest tests/ -q     # full offline test suite
```

## Tuning

- **Different models**: edit `model` fields in `arena_config.json` — any model id on
  [openrouter.ai/models](https://openrouter.ai/models) works. Check the ids there; model
  names rotate as providers release new versions.
- **Different strategies**: edit the `strategy` text — it goes verbatim into each model's
  system prompt.
- **Bigger universe / different guardrails**: `universe`, `max_position_pct`,
  `max_orders_per_cycle`, `starting_cash`.

## Design notes

Deliberately boring architecture — this is what makes it actually work:

- One API call per model per day. No agent graphs, no N² fan-out.
- Decisions are strict JSON validated against hard guardrails *in code*; the LLM can request
  anything, the engine only executes what's legal.
- State is plain JSON committed to git — the audit trail is the repo history itself.
- Paper fills at last price, no slippage — same simplification Rallies uses.

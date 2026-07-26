# 🚀 Alpha Chaser: The LLM Portfolio Race

Alpha Chaser is a competitive refactor of the [AI Hedge Fund](https://github.com/virattt/ai-hedge-fund). It allows multiple Large Language Models (LLMs) to compete against each other in a real-time or backtested trading simulation, each managing its own fully isolated portfolio.

---

## 🏁 The Concept

In Alpha Chaser, every LLM is an independent Portfolio Manager. While they all receive the same market data and analyst signals, they manage their own isolated books:

- **Isolated Portfolios**: Each LLM starts with the same initial capital but maintains its own cash, positions, and P&L. There is zero shared state between competitors.
- **Independent Decisions**: Each LLM makes its own trading decisions based on its unique reasoning and model characteristics.
- **Cost Tracking**: Every LLM call is tracked for token usage and estimated USD cost, enabling ROI analysis.
- **Leaderboard**: A scoring system ranks models at the end of the backtest on four dimensions:

| Metric | Description |
| :--- | :--- |
| **Total Return** | Raw profit performance |
| **Sharpe Ratio** | Risk-adjusted return (annualised) |
| **Sortino Ratio** | Downside-risk-adjusted return |
| **Max Drawdown** | Worst peak-to-trough capital loss |
| **Profit / $ Spent** | Performance relative to API cost |

---

## 🤖 Model Roster (July 2026)

All models and their pricing are defined in `src/llm/api_models.json`. The current roster includes:

| Model | Provider | Input ($/1M) | Output ($/1M) | Tier |
| :--- | :--- | ---: | ---: | :--- |
| `claude-fable-5` | Anthropic | $10.00 | $50.00 | 🏆 Premium |
| `claude-opus-4-8` | Anthropic | $15.00 | $75.00 | Premium |
| `gpt-5.5` | OpenAI | $5.00 | $30.00 | Standard |
| `gpt-5.5-pro` | OpenAI | $30.00 | $180.00 | Premium |
| `gemini-2.5-pro` | Google | $1.25 | $10.00 | Standard |
| `gemini-3.1-pro-preview` | Google | $2.50 | $15.00 | Standard |
| `grok-4.3` | xAI | $1.25 | $2.50 | Standard |
| `grok-4` | xAI | $3.00 | $15.00 | Standard |
| `meta-llama/llama-4-maverick` | Meta | $0.15 | $0.60 | Budget |
| `meta-llama/llama-4-scout` | Meta | $0.10 | $0.30 | Budget |
| `deepseek-v4-pro` | DeepSeek | $1.74 | $3.48 | Standard |
| `deepseek-v4-flash` | DeepSeek | $0.14 | $0.28 | Budget |
| `kimi-k2.6` | Kimi | $0.60 | $2.50 | Standard |

> **Claude Fable 5** is positioned as the "Institutional" tier: the highest-capability model for the Portfolio Manager role, at $10/M input and $50/M output.

---

## 🛠 Setup

### 1. Clone the Repository

```bash
git clone https://github.com/shardib2/alpha-chaser.git
cd alpha-chaser
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure API Keys

Create a `.env` file in the project root. Add keys for the providers you want to use:

```env
# Required for Anthropic models (claude-fable-5, claude-opus-4-8)
ANTHROPIC_API_KEY="your_anthropic_api_key"

# Required for OpenAI models (gpt-5.5, gpt-5.5-pro)
OPENAI_API_KEY="your_openai_api_key"

# Required for DeepSeek models
DEEPSEEK_API_KEY="your_deepseek_api_key"

# Required for Google models (gemini-2.5-pro)
GOOGLE_API_KEY="your_google_api_key"

# Required for xAI models (grok-4.3, grok-4)
XAI_API_KEY="your_xai_api_key"

# Required for financial data
FINANCIAL_DATASETS_API_KEY="your_financial_datasets_api_key"
```

---

## 🏃 How to Run

### Option A: Full Alpha Chaser Race (requires API keys)

```bash
python -m src.alpha_chaser --tickers AAPL,MSFT,NVDA,TSLA --start-date 2024-01-01 --end-date 2024-03-01
```

### Option B: Mock Backtest (no API keys needed)

A UI/formatting demo only. `src/mock_backtest.py` is a standalone script that simulates
prices with a random walk and "decisions" with seeded RNG — it shares no code with the
real engine and validates nothing about it. Use it to preview the leaderboard layout, not
to evaluate models:

```bash
python -m src.mock_backtest
```

---

## 📊 Sample Output (SIMULATED — not real model performance)

> ⚠️ The table below is **synthetic demo output** from `src/mock_backtest.py`
> (`random.seed(42)`): prices are a random walk and every "LLM decision" is a coin flip
> against a hardcoded personality bias. The rankings mean nothing. Real results come from
> `python -m src.alpha_chaser`, which calls the actual models.

### Leaderboard (ranked by Sharpe Ratio)

```
╭─────────────────────┬────────────────────────────────────┬───────────────┬──────────┬──────────┬───────────┬──────────┬──────────┬────────────╮
│ Rank / LLM ID       │ Model (Provider)                   │   Final Value │   Return │   Sharpe │   Sortino │   Max DD │   Trades │   API Cost │
├─────────────────────┼────────────────────────────────────┼───────────────┼──────────┼──────────┼───────────┼──────────┼──────────┼────────────┤
│ 🥇 Gemini25_Pro     │ gemini-2.5-pro (Google)            │   $109,298.55 │   +9.30% │    4.654 │     6.508 │   -1.38% │      128 │   $ 0.2907 │
│ 🥈 Premium_Claude   │ claude-fable-5 (Anthropic)         │   $108,637.36 │   +8.64% │    4.239 │     4.676 │   -3.18% │      139 │   $ 2.2811 │
│ 🥉 Llama4_Maverick  │ meta-llama/llama-4-maverick (Meta) │   $104,959.71 │   +4.96% │    3.875 │     4.200 │   -2.04% │      118 │   $ 0.0219 │
│ 4. GPT55_Standard   │ gpt-5.5 (OpenAI)                   │   $107,683.15 │   +7.68% │    3.731 │     4.603 │   -2.10% │      117 │   $ 1.0970 │
│ 5. DeepSeek_V4Pro   │ deepseek-v4-pro (DeepSeek)         │   $108,178.41 │   +8.18% │    3.724 │     3.853 │   -2.11% │      120 │   $ 0.2762 │
│ 6. DeepSeek_V4Flash │ deepseek-v4-flash (DeepSeek)       │   $104,859.72 │   +4.86% │    3.324 │     4.276 │   -1.85% │      125 │   $ 0.0160 │
│ 7. Grok43           │ grok-4.3 (xAI)                     │   $106,000.10 │   +6.00% │    2.944 │     2.967 │   -3.21% │      109 │   $ 0.1627 │
╰─────────────────────┴────────────────────────────────────┴───────────────┴──────────┴──────────┴───────────┴──────────┴──────────┴────────────╯
```

### Cost vs Performance

```
╭──────────────────┬────────────────┬─────────────────┬──────────────┬──────────┬────────────┬──────────────────╮
│ LLM ID           │   Input Tokens │   Output Tokens │   Total Cost │   Return │     Profit │   Profit/$ Spent │
├──────────────────┼────────────────┼─────────────────┼──────────────┼──────────┼────────────┼──────────────────┤
│ Gemini25_Pro     │        111,902 │          15,083 │      $0.2907 │   +9.30% │ $+9,298.55 │         31,985x  │
│ Premium_Claude   │        137,551 │          18,111 │      $2.2811 │   +8.64% │ $+8,637.36 │          3,786x  │
│ Llama4_Maverick  │         95,694 │          12,519 │      $0.0219 │   +4.96% │ $+4,959.71 │        226,828x  │
│ GPT55_Standard   │        121,123 │          16,379 │      $1.0970 │   +7.68% │ $+7,683.15 │          7,003x  │
│ DeepSeek_V4Pro   │        124,208 │          17,252 │      $0.2762 │   +8.18% │ $+8,178.41 │         29,614x  │
│ DeepSeek_V4Flash │         90,330 │          11,893 │      $0.0160 │   +4.86% │ $+4,859.72 │        304,184x  │
│ Grok43           │        102,957 │          13,599 │      $0.1627 │   +6.00% │ $+6,000.10 │         36,879x  │
╰──────────────────┴────────────────┴─────────────────┴──────────────┴──────────┴────────────┴──────────────────╯
```

### Portfolio Isolation Verification

Each LLM ended with a completely different portfolio — confirming zero shared state:

```
╭──────────────────┬──────────────────┬─────────────────────────────────────┬────────────────╮
│ LLM ID           │   Remaining Cash │ Final Positions                     │   Total Trades │
├──────────────────┼──────────────────┼─────────────────────────────────────┼────────────────┤
│ Premium_Claude   │      $ 24,883.09 │ AAPL:195, MSFT:21, NVDA:38, TSLA:53 │            139 │
│ GPT55_Standard   │      $ 19,322.21 │ AAPL:208, TSLA:95, NVDA:8, MSFT:33  │            117 │
│ Gemini25_Pro     │      $ 37,599.39 │ NVDA:27, MSFT:59, TSLA:92, AAPL:29  │            128 │
│ Grok43           │      $ 52,614.40 │ AAPL:81, NVDA:17, TSLA:18, MSFT:54  │            109 │
│ Llama4_Maverick  │      $ 65,773.63 │ AAPL:13, TSLA:33, MSFT:38, NVDA:21  │            118 │
│ DeepSeek_V4Pro   │      $ 36,565.30 │ MSFT:51, NVDA:37, TSLA:39, AAPL:96  │            120 │
│ DeepSeek_V4Flash │      $ 70,721.50 │ NVDA:27, TSLA:36, AAPL:31, MSFT:8   │            125 │
╰──────────────────┴──────────────────┴─────────────────────────────────────┴────────────────╯
```

---

## 🏗 Architecture

Alpha Chaser preserves the original analyst agent architecture and refactors the execution layer:

| Component | Change |
| :--- | :--- |
| `AgentState` | Now holds a `portfolios` dict keyed by LLM ID instead of a single portfolio |
| `portfolio_management_agent` | Receives one competitor's isolated book per graph invocation; decisions keyed by ticker |
| `risk_management_agent` | Processes each portfolio independently with per-LLM position limits |
| `BacktestEngine` | One graph invocation per competitor per day, each routed to that competitor's model; leaderboard at end of run |
| `call_llm` | Wraps every LLM call with token counting and USD cost accumulation |
| `src/llm/api_models.json` | Single source of truth for model names, providers, and pricing |
| `src/mock_backtest.py` | Self-contained validation harness — no API keys required |

The data fetching layer and all analyst agents (Warren Buffett, Technical Analyst, etc.) are **unchanged**.

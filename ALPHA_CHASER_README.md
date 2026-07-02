# 🚀 Alpha Chaser: The LLM Portfolio Race

Alpha Chaser is a competitive refactor of the AI Hedge Fund. It allows multiple Large Language Models (LLMs) to compete against each other in a real-time or backtested trading simulation.

## 🏁 The Concept

In Alpha Chaser, every LLM is an independent Portfolio Manager. While they all receive the same market data and analyst signals, they manage their own isolated books:
- **Isolated Portfolios**: Each LLM starts with the same initial capital but maintains its own cash, positions, and P&L.
- **Independent Decisions**: Each LLM makes its own trading decisions based on its unique "personality" and reasoning.
- **Leaderboard**: A real-time scoring system ranks models based on:
  - **Total Return**: Pure profit performance.
  - **Sharpe Ratio**: Risk-adjusted return.
  - **Sortino Ratio**: Downside-risk-adjusted return.
  - **Max Drawdown**: Capital preservation.
  - **ROI**: Performance vs. LLM token cost.

## 🤖 The Competitors

The default roster includes:
1. **Claude Fable 5 (Premium)**: The high-end "Institutional" model ($10/M input, $50/M output).
2. **GPT-4o (Standard)**: The reliable industry benchmark.
3. **DeepSeek V4 Pro (Challenger)**: The aggressive, low-cost competitor.
4. **User Selection**: Your chosen model from the CLI.

## 🛠 How to Run

To start the Alpha Chaser race, you'll need to set up your API keys for the various LLM providers. Create a `.env` file in the root directory of the project with the following:

```
ANTHROPIC_API_KEY="your_anthropic_api_key"
OPENAI_API_KEY="your_openai_api_key"
DEEPSEEK_API_KEY="your_deepseek_api_key"
# Add other API keys as needed for additional models
```

Then, you can run the Alpha Chaser:

```bash
python -m src.alpha_chaser --tickers AAPL,MSFT,NVDA,GOOGL --start-date 2024-01-01 --end-date 2024-03-01
```

## 📊 Leaderboard Example

At the end of the run, you'll see a leaderboard like this:

| LLM ID | Model | Total Return | Sharpe | Sortino | Max DD | Cost |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Premium_Claude | claude-fable-5 | +12.4% | 2.1 | 2.8 | -4.2% | $1.20 |
| GPT_Standard | gpt-4o | +8.1% | 1.5 | 1.9 | -6.5% | $0.45 |
| ... | ... | ... | ... | ... | ... | ... |

## 🏗 Architecture

Alpha Chaser maintains the core analyst agent architecture but refactors the `AgentState` and `BacktestEngine`:
- **AgentState**: Now holds a `portfolios` dictionary keyed by LLM ID.
- **Risk Manager**: Processes each portfolio independently, adjusting limits based on that specific LLM's current holdings.
- **Portfolio Manager**: Loops through each LLM, providing isolated decision-making.
- **Cost Tracker**: Wraps LLM calls to track token usage and estimated USD cost per model.

# Alpha Chaser Architecture Design

This document outlines the architectural changes required to refactor the existing AI Hedge Fund into "Alpha Chaser," a system enabling multiple LLMs to manage independent portfolios and compete against each other.

## 1. Multi-Portfolio State Refactor

**Current State:** The `AgentState` (defined in `src/graph/state.py`) currently holds a single `data["portfolio"]` dictionary, representing a single portfolio. The `metadata` also stores a single `model_name` and `model_provider`.

**Proposed Change:**

*   **`AgentState` Modification:** The `AgentState` will be updated to store a dictionary of portfolios, where each key is a unique LLM identifier (e.g., `llm_id`) and the value is a `Portfolio` object. This will be represented as `data["llm_portfolios"]: Dict[str, Portfolio]`. The `data` dictionary will also contain a list of `llm_ids` to iterate over.
*   **`metadata` Enhancement:** The `metadata` will be extended to include LLM-specific configurations. Instead of global `model_name` and `model_provider`, `metadata` will contain `llm_configs: Dict[str, Dict[str, str]]`, mapping each `llm_id` to its specific `model_name` and `model_provider`.

## 2. Isolated Execution

**Current State:** Both `portfolio_management_agent` and `risk_management_agent` operate on a single, shared `portfolio` within the `AgentState`.

**Proposed Change:**

*   **Agent Iteration:** The `portfolio_management_agent` (in `src/agents/portfolio_manager.py`) and `risk_management_agent` (in `src/agents/risk_manager.py`) will be refactored to iterate through the `data["llm_portfolios"]` dictionary. For each `llm_id` and its corresponding `Portfolio` object, the agents will perform their calculations and decision-making processes independently.
*   **Data Isolation:** Each LLM will receive its own isolated view of its portfolio (cash, positions, P&L) for decision-making. This ensures that trading decisions made by one LLM do not directly affect the capital or holdings of another.
*   **Analyst Signals:** Analyst signals will continue to be generated centrally and provided to all LLMs, ensuring they operate on the same market intelligence.

## 3. Claude Fable 5 Integration and Cost Tracking

**Current State:** The system supports various LLM providers, but `claude-fable-5` is not explicitly listed, and there is no mechanism for cost tracking.

**Proposed Change:**

*   **Claude Fable 5 Addition:**
    *   Add `claude-fable-5` as a model option under the `ANTHROPIC` provider in `src/llm/models.py` and `src/llm/api_models.json`.
    *   Update `src/llm/models.py` to correctly instantiate `ChatAnthropic` for `claude-fable-5`.
*   **Cost Tracking Wrapper:**
    *   A wrapper function or decorator will be implemented around `src/utils/llm.py::call_llm`.
    *   This wrapper will intercept LLM calls, track input and output tokens, and estimate costs based on predefined token pricing for each model (e.g., $10/M input, $50/M output for Claude Fable 5).
    *   Cost data will be stored in the `AgentState` (e.g., `metadata["llm_costs"]: Dict[str, Dict[str, float]]`) per LLM ID and accumulated over the backtest period.

## 4. BacktestEngine Refactor for Parallel Execution and Leaderboard

**Current State:** The `BacktestEngine` (in `src/backtesting/engine.py`) is designed to run a backtest for a single `agent` and a single `portfolio`.

**Proposed Change:**

*   **Multi-Portfolio Management:** The `BacktestEngine` will be refactored to manage multiple `Portfolio` instances, one for each competing LLM. Instead of `self._portfolio`, it will maintain `self._llm_portfolios: Dict[str, Portfolio]`.
*   **Parallel Execution:** The daily backtest loop will iterate through each `llm_id` and its corresponding `Portfolio`. For each LLM, it will:
    *   Invoke the `agent_controller` with the specific LLM's configuration and portfolio state.
    *   Execute trades for that LLM's portfolio.
    *   Calculate portfolio value and exposures for that LLM.
*   **Leaderboard Scoring:**
    *   After the backtest period, for each LLM's portfolio, the `PerformanceMetricsCalculator` (in `src/backtesting/metrics.py`) will be used to compute:
        *   **Sharpe Ratio:** Measures risk-adjusted return.
        *   **Sortino Ratio:** Similar to Sharpe, but only considers downside deviation.
        *   **Max Drawdown:** The largest peak-to-trough decline in portfolio value.
        *   **Total Return:** The overall percentage gain or loss.
    *   These metrics, along with the accumulated costs, will be compiled into a leaderboard, ranking LLMs based on their performance. The leaderboard will be part of the final backtest output.

## 5. README Update

A `README.md` will be added to the root of the `alpha-chaser` repository, explaining the concept of Alpha Chaser, its architecture, and instructions on how to configure and run backtests with competing LLMs and view the leaderboard results.

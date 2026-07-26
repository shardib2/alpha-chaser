from __future__ import annotations

from datetime import datetime
from typing import Sequence, Dict, List

import pandas as pd
from dateutil.relativedelta import relativedelta

from .controller import AgentController
from .trader import TradeExecutor
from .metrics import PerformanceMetricsCalculator
from .portfolio import Portfolio
from .types import PerformanceMetrics, PortfolioValuePoint
from .valuation import calculate_portfolio_value, compute_exposures
from .output import OutputBuilder
from .benchmarks import BenchmarkCalculator

from src.tools.api import (
    get_company_news,
    get_price_data,
    get_prices,
    get_financial_metrics,
    get_insider_trades,
)


class BacktestEngine:
    """Coordinates the Alpha Chaser backtest loop where multiple LLMs compete."""

    def __init__(
        self,
        *,
        agent,
        tickers: list[str],
        start_date: str,
        end_date: str,
        initial_capital: float,
        llm_configs: Dict[str, Dict[str, str]] | None = None, # Map of llm_id -> {model_name, model_provider}
        selected_analysts: list[str] | None,
        initial_margin_requirement: float,
        model_name: str | None = None,
        model_provider: str | None = None,
    ) -> None:
        # Legacy single-model callers (backtester.py, backtesting/cli.py, tests)
        # pass model_name/model_provider; wrap them as a one-competitor race.
        if llm_configs is None:
            if not model_name or not model_provider:
                raise ValueError("Provide either llm_configs or model_name+model_provider")
            llm_configs = {"default": {"model_name": model_name, "model_provider": model_provider}}
        self._agent = agent
        self._tickers = tickers
        self._start_date = start_date
        self._end_date = end_date
        self._initial_capital = float(initial_capital)
        self._llm_configs = llm_configs
        self._selected_analysts = selected_analysts

        # Alpha Chaser: Initialize isolated portfolios for each LLM
        self._portfolios: Dict[str, Portfolio] = {
            llm_id: Portfolio(
                tickers=tickers,
                initial_cash=initial_capital,
                margin_requirement=initial_margin_requirement,
            )
            for llm_id in llm_configs
        }
        
        self._executor = TradeExecutor()
        self._agent_controller = AgentController()
        self._perf_calculator = PerformanceMetricsCalculator()
        self._results_builder = OutputBuilder(initial_capital=self._initial_capital)
        self._benchmark = BenchmarkCalculator()

        # Track values and metrics per LLM
        self._llm_portfolio_values: Dict[str, list[PortfolioValuePoint]] = {llm_id: [] for llm_id in llm_configs}
        self._llm_performance_metrics: Dict[str, PerformanceMetrics] = {
            llm_id: {
                "sharpe_ratio": None,
                "sortino_ratio": None,
                "max_drawdown": None,
                "long_short_ratio": None,
                "gross_exposure": None,
                "net_exposure": None,
                "total_return": 0.0,
            }
            for llm_id in llm_configs
        }
        
        self._table_rows: list[list] = []

    def _prefetch_data(self) -> None:
        end_date_dt = datetime.strptime(self._end_date, "%Y-%m-%d")
        start_date_dt = end_date_dt - relativedelta(years=1)
        start_date_str = start_date_dt.strftime("%Y-%m-%d")

        for ticker in self._tickers:
            get_prices(ticker, start_date_str, self._end_date)
            get_financial_metrics(ticker, self._end_date, limit=10)
            get_insider_trades(ticker, self._end_date, start_date=self._start_date, limit=1000)
            get_company_news(ticker, self._end_date, start_date=self._start_date, limit=1000)
        
        get_prices("SPY", self._start_date, self._end_date)

    def run_backtest(self) -> Dict[str, PerformanceMetrics]:
        self._prefetch_data()

        dates = pd.date_range(self._start_date, self._end_date, freq="B")
        
        # Initialize starting values
        if len(dates) > 0:
            for llm_id in self._llm_configs:
                self._llm_portfolio_values[llm_id] = [
                    {"Date": dates[0], "Portfolio Value": self._initial_capital}
                ]

        for current_date in dates:
            lookback_start = (current_date - relativedelta(months=1)).strftime("%Y-%m-%d")
            current_date_str = current_date.strftime("%Y-%m-%d")
            previous_date_str = (current_date - relativedelta(days=1)).strftime("%Y-%m-%d")
            
            if lookback_start == current_date_str:
                continue

            # Fetch prices once for the day
            current_prices: Dict[str, float] = {}
            missing_data = False
            for ticker in self._tickers:
                try:
                    price_data = get_price_data(ticker, previous_date_str, current_date_str)
                    if price_data.empty:
                        missing_data = True
                        break
                    current_prices[ticker] = float(price_data.iloc[-1]["close"])
                except Exception:
                    missing_data = True
                    break
            if missing_data:
                continue

            # Alpha Chaser: Run each LLM independently against its own portfolio.
            # Each competitor gets ONE graph invocation with ONLY its own book,
            # keyed by llm_id so risk/portfolio agents attribute state correctly
            # and decisions come back keyed by ticker.
            first_llm = next(iter(self._llm_configs))
            display_output: Dict | None = None
            display_trades: Dict[str, int] = {}

            for llm_id, config in self._llm_configs.items():
                portfolio = self._portfolios[llm_id]

                agent_output = self._agent_controller.run_agent(
                    self._agent,
                    tickers=self._tickers,
                    start_date=lookback_start,
                    end_date=current_date_str,
                    portfolio={llm_id: portfolio.get_snapshot()},
                    model_name=config["model_name"],
                    model_provider=config["model_provider"],
                    selected_analysts=self._selected_analysts,
                )

                decisions = agent_output["decisions"]
                executed_trades: Dict[str, int] = {}
                for ticker in self._tickers:
                    d = decisions.get(ticker, {"action": "hold", "quantity": 0})
                    action = d.get("action", "hold")
                    qty = d.get("quantity", 0)
                    executed_qty = self._executor.execute_trade(ticker, action, qty, current_prices[ticker], portfolio)
                    executed_trades[ticker] = executed_qty

                if llm_id == first_llm:
                    display_output = agent_output
                    display_trades = dict(executed_trades)

                total_value = calculate_portfolio_value(portfolio, current_prices)
                exposures = compute_exposures(portfolio, current_prices)

                point: PortfolioValuePoint = {
                    "Date": current_date,
                    "Portfolio Value": total_value,
                    "Long Exposure": exposures["Long Exposure"],
                    "Short Exposure": exposures["Short Exposure"],
                    "Gross Exposure": exposures["Gross Exposure"],
                    "Net Exposure": exposures["Net Exposure"],
                    "Long/Short Ratio": exposures["Long/Short Ratio"],
                }
                self._llm_portfolio_values[llm_id].append(point)
                
                # Update metrics
                if len(self._llm_portfolio_values[llm_id]) > 3:
                    computed = self._perf_calculator.compute_metrics(self._llm_portfolio_values[llm_id])
                    if computed:
                        self._llm_performance_metrics[llm_id].update(computed)
                
                # Alpha Chaser: Accumulate costs from agent output.
                # The whole invocation ran for this competitor, so every cost entry
                # (analysts keyed by agent name + portfolio manager keyed by llm_id)
                # belongs to it. Each day's run starts a fresh state, so add, don't assign.
                day_costs = agent_output.get("metadata", {}).get("llm_costs", {})
                day_total = sum(c.get("total_cost", 0.0) for c in day_costs.values())
                prior = self._llm_performance_metrics[llm_id].get("total_cost") or 0.0
                self._llm_performance_metrics[llm_id]["total_cost"] = prior + day_total

                # Calculate total return
                self._llm_performance_metrics[llm_id]["total_return"] = (total_value / self._initial_capital - 1) * 100

            # Print daily progress (using the first LLM as the representative for terminal output)
            # A full leaderboard will be printed at the end
            if display_output is None:
                continue
            rows = self._results_builder.build_day_rows(
                date_str=current_date_str,
                tickers=self._tickers,
                agent_output=display_output,
                executed_trades=display_trades,
                current_prices=current_prices,
                portfolio=self._portfolios[first_llm],
                performance_metrics=self._llm_performance_metrics[first_llm],
                total_value=calculate_portfolio_value(self._portfolios[first_llm], current_prices),
                benchmark_return_pct=self._benchmark.get_return_pct("SPY", self._start_date, current_date_str),
            )
            self._table_rows = rows + self._table_rows
            self._results_builder.print_rows(self._table_rows)

        # Print Final Leaderboard
        self._print_leaderboard()
        return self._llm_performance_metrics

    def _print_leaderboard(self):
        from tabulate import tabulate
        from colorama import Fore, Style
        
        print(f"\n{Fore.WHITE}{Style.BRIGHT}🏆 ALPHA CHASER LEADERBOARD 🏆{Style.RESET_ALL}")
        
        # Sort on the numeric return, then format for display
        ranked = sorted(
            self._llm_performance_metrics.items(),
            key=lambda kv: kv[1].get("total_return", 0.0) or 0.0,
            reverse=True,
        )

        leaderboard_data = []
        for llm_id, metrics in ranked:
            config = self._llm_configs[llm_id]
            ret = metrics.get("total_return", 0.0)
            sharpe = metrics.get("sharpe_ratio")
            sortino = metrics.get("sortino_ratio")
            mdd = metrics.get("max_drawdown")
            cost = metrics.get("total_cost", 0.0)

            ret_color = Fore.GREEN if ret >= 0 else Fore.RED

            leaderboard_data.append([
                llm_id,
                f"{config['model_name']} ({config['model_provider']})",
                f"{ret_color}{ret:+.2f}%{Style.RESET_ALL}",
                f"{sharpe:.2f}" if sharpe is not None else "N/A",
                f"{sortino:.2f}" if sortino is not None else "N/A",
                f"{Fore.RED}{mdd:.2f}%{Style.RESET_ALL}" if mdd is not None else "N/A",
                f"${cost:.4f}"
            ])

        print(tabulate(
            leaderboard_data,
            headers=["LLM ID", "Model", "Total Return", "Sharpe", "Sortino", "Max DD", "Cost"],
            tablefmt="grid",
            colalign=("left", "left", "right", "right", "right", "right", "right")
        ))
        print("\n")

    def get_portfolio_values(self, llm_id: str | None = None) -> Sequence[PortfolioValuePoint]:
        if llm_id is None:
            llm_id = next(iter(self._llm_configs))
        return list(self._llm_portfolio_values.get(llm_id, []))

    @property
    def _portfolio(self) -> Portfolio:
        """Legacy accessor for single-competitor runs (old CLI and tests)."""
        if len(self._portfolios) != 1:
            raise AttributeError("_portfolio is only available for single-LLM runs; use _portfolios[llm_id]")
        return next(iter(self._portfolios.values()))

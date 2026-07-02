from langchain_core.messages import HumanMessage
from src.graph.state import AgentState, show_agent_reasoning
from src.utils.progress import progress
from src.tools.api import get_prices, prices_to_df
import json
import numpy as np
import pandas as pd
from src.utils.api_key import get_api_key_from_state

##### Risk Management Agent #####
def risk_management_agent(state: AgentState, agent_id: str = "risk_management_agent"):
    """Controls position sizing based on volatility-adjusted risk factors for multiple tickers."""
    # Alpha Chaser: Handle multiple portfolios if present
    if "portfolios" in state["data"]:
        llm_portfolios = state["data"]["portfolios"]
        # If this agent_id corresponds to a specific LLM, use that portfolio
        if agent_id.startswith("risk_management_agent_"):
            llm_id = agent_id.replace("risk_management_agent_", "")
            portfolios_to_process = {llm_id: llm_portfolios.get(llm_id, {})}
        else:
            portfolios_to_process = llm_portfolios
    else:
        # Fallback to single portfolio for backward compatibility
        portfolios_to_process = {"portfolio_manager": state["data"].get("portfolio", {})}

    data = state["data"]
    tickers = data["tickers"]
    api_key = get_api_key_from_state(state, "FINANCIAL_DATASETS_API_KEY")
    
    # Initialize shared price and volatility data across all portfolios
    current_prices = {}
    volatility_data = {}
    returns_by_ticker: dict[str, pd.Series] = {}

    # Pre-fetch data once for all tickers across all portfolios
    all_tickers = set(tickers)
    for p in portfolios_to_process.values():
        all_tickers |= set(p.get("positions", {}).keys())
    
    for ticker in all_tickers:
        progress.update_status(agent_id, ticker, "Fetching price data and calculating volatility")
        prices = get_prices(ticker=ticker, start_date=data["start_date"], end_date=data["end_date"], api_key=api_key)

        if not prices:
            volatility_data[ticker] = {"daily_volatility": 0.05, "annualized_volatility": 0.05 * np.sqrt(252), "volatility_percentile": 100, "data_points": 0}
            continue

        prices_df = prices_to_df(prices)
        if not prices_df.empty and len(prices_df) > 1:
            current_price = prices_df["close"].iloc[-1]
            current_prices[ticker] = current_price
            vol_metrics = calculate_volatility_metrics(prices_df)
            volatility_data[ticker] = vol_metrics
            daily_returns = prices_df["close"].pct_change().dropna()
            if len(daily_returns) > 0:
                returns_by_ticker[ticker] = daily_returns
        else:
            current_prices[ticker] = 0
            volatility_data[ticker] = {"daily_volatility": 0.05, "annualized_volatility": 0.05 * np.sqrt(252), "volatility_percentile": 100, "data_points": len(prices_df) if not prices_df.empty else 0}

    correlation_matrix = None
    if len(returns_by_ticker) >= 2:
        try:
            returns_df = pd.DataFrame(returns_by_ticker).dropna(how="any")
            if returns_df.shape[1] >= 2 and returns_df.shape[0] >= 5:
                correlation_matrix = returns_df.corr()
        except Exception:
            pass

    # Process each portfolio independently
    for current_llm_id, portfolio in portfolios_to_process.items():
        display_id = f"risk_management_agent_{current_llm_id}"
        risk_analysis = {}
        
        # Calculate total portfolio value
        total_portfolio_value = portfolio.get("cash", 0.0)
        for ticker, position in portfolio.get("positions", {}).items():
            if ticker in current_prices:
                total_portfolio_value += (position.get("long", 0) - position.get("short", 0)) * current_prices[ticker]
        
        active_positions = {t for t, pos in portfolio.get("positions", {}).items() if abs(pos.get("long", 0) - pos.get("short", 0)) > 0}

        for ticker in tickers:
            if ticker not in current_prices or current_prices[ticker] <= 0:
                risk_analysis[ticker] = {"remaining_position_limit": 0.0, "current_price": 0.0, "reasoning": {"error": "Missing price data"}}
                continue
                
            current_price = current_prices[ticker]
            vol_data = volatility_data.get(ticker, {})
            position = portfolio.get("positions", {}).get(ticker, {})
            current_position_value = abs(position.get("long", 0) - position.get("short", 0)) * current_price
            
            vol_adjusted_limit_pct = calculate_volatility_adjusted_limit(vol_data.get("annualized_volatility", 0.25))

            corr_metrics = {"avg_correlation_with_active": None, "max_correlation_with_active": None, "top_correlated_tickers": []}
            corr_multiplier = 1.0
            if correlation_matrix is not None and ticker in correlation_matrix.columns:
                comparable = [t for t in active_positions if t in correlation_matrix.columns and t != ticker] or [t for t in correlation_matrix.columns if t != ticker]
                if comparable:
                    series = correlation_matrix.loc[ticker, comparable].dropna()
                    if len(series) > 0:
                        avg_corr, max_corr = float(series.mean()), float(series.max())
                        corr_metrics.update({"avg_correlation_with_active": avg_corr, "max_correlation_with_active": max_corr})
                        top_corr = series.sort_values(ascending=False).head(3)
                        corr_metrics["top_correlated_tickers"] = [{"ticker": idx, "correlation": float(val)} for idx, val in top_corr.items()]
                        corr_multiplier = calculate_correlation_multiplier(avg_corr)
            
            combined_limit_pct = vol_adjusted_limit_pct * corr_multiplier
            position_limit = total_portfolio_value * combined_limit_pct
            remaining_position_limit = position_limit - current_position_value
            max_position_size = max(0.0, min(remaining_position_limit, portfolio.get("cash", 0)))
            
            risk_analysis[ticker] = {
                "remaining_position_limit": float(max_position_size),
                "current_price": float(current_price),
                "volatility_metrics": {
                    "daily_volatility": float(vol_data.get("daily_volatility", 0.05)),
                    "annualized_volatility": float(vol_data.get("annualized_volatility", 0.25)),
                    "volatility_percentile": float(vol_data.get("volatility_percentile", 100)),
                    "data_points": int(vol_data.get("data_points", 0))
                },
                "correlation_metrics": corr_metrics,
                "reasoning": {
                    "portfolio_value": float(total_portfolio_value),
                    "current_position_value": float(current_position_value),
                    "base_position_limit_pct": float(vol_adjusted_limit_pct),
                    "correlation_multiplier": float(corr_multiplier),
                    "combined_position_limit_pct": float(combined_limit_pct),
                    "position_limit": float(position_limit),
                    "remaining_limit": float(remaining_position_limit),
                    "available_cash": float(portfolio.get("cash", 0)),
                    "risk_adjustment": f"Volatility x Correlation adjusted: {combined_limit_pct:.1%} (base {vol_adjusted_limit_pct:.1%})"
                },
            }
            progress.update_status(display_id, ticker, f"Adj. limit: {combined_limit_pct:.1%}, Available: ${max_position_size:.0f}")

        progress.update_status(display_id, None, "Done")
        if state["metadata"].get("show_reasoning"):
            show_agent_reasoning(risk_analysis, f"Risk Manager ({current_llm_id})")
        state["data"]["analyst_signals"][display_id] = risk_analysis

    return {"messages": state["messages"], "data": data}

def calculate_volatility_metrics(prices_df: pd.DataFrame, lookback_days: int = 60) -> dict:
    if len(prices_df) < 2:
        return {"daily_volatility": 0.05, "annualized_volatility": 0.05 * np.sqrt(252), "volatility_percentile": 100, "data_points": len(prices_df)}
    daily_returns = prices_df["close"].pct_change().dropna()
    if len(daily_returns) < 2:
        return {"daily_volatility": 0.05, "annualized_volatility": 0.05 * np.sqrt(252), "volatility_percentile": 100, "data_points": len(daily_returns)}
    recent_returns = daily_returns.tail(min(lookback_days, len(daily_returns)))
    daily_vol = recent_returns.std()
    annualized_vol = daily_vol * np.sqrt(252)
    current_vol_percentile = (daily_returns.rolling(window=30).std().dropna() <= daily_vol).mean() * 100 if len(daily_returns) >= 30 else 50
    return {
        "daily_volatility": float(daily_vol) if not np.isnan(daily_vol) else 0.025,
        "annualized_volatility": float(annualized_vol) if not np.isnan(annualized_vol) else 0.25,
        "volatility_percentile": float(current_vol_percentile) if not np.isnan(current_vol_percentile) else 50.0,
        "data_points": len(recent_returns)
    }

def calculate_volatility_adjusted_limit(annualized_volatility: float) -> float:
    base_limit = 0.20
    if annualized_volatility < 0.15: vol_multiplier = 1.25
    elif annualized_volatility < 0.30: vol_multiplier = 1.0 - (annualized_volatility - 0.15) * 0.5
    elif annualized_volatility < 0.50: vol_multiplier = 0.75 - (annualized_volatility - 0.30) * 0.5
    else: vol_multiplier = 0.50
    return base_limit * max(0.25, min(1.25, vol_multiplier))

def calculate_correlation_multiplier(avg_correlation: float) -> float:
    if avg_correlation >= 0.80: return 0.70
    if avg_correlation >= 0.60: return 0.85
    if avg_correlation >= 0.40: return 1.00
    if avg_correlation >= 0.20: return 1.05
    return 1.10

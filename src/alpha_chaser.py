import sys
from colorama import Fore, Style
from src.main import run_hedge_fund
from src.backtesting.engine import BacktestEngine
from src.cli.input import parse_cli_inputs

def run_alpha_chaser():
    """Run the Alpha Chaser competitive backtest."""
    inputs = parse_cli_inputs(
        description="Run Alpha Chaser - Competitive LLM Portfolio Racing",
        require_tickers=True,
        default_months_back=1,
        include_graph_flag=False,
        include_reasoning_flag=False,
    )

    # Define the roster of competitors
    # In a real Alpha Chaser run, we want multiple different LLMs
    # We'll use the user's selected model as one, and add others for competition
    llm_configs = {
        "Premium_Claude": {"model_name": "claude-fable-5", "model_provider": "Anthropic"},
        "GPT_Standard": {"model_name": "gpt-4o", "model_provider": "OpenAI"},
        "DeepSeek_Challenger": {"model_name": "deepseek-v4-pro", "model_provider": "DeepSeek"},
        "User_Selection": {"model_name": inputs.model_name, "model_provider": inputs.model_provider},
    }

    print(f"\n{Fore.CYAN}{Style.BRIGHT}🚀 Starting Alpha Chaser: Multi-LLM Portfolio Race{Style.RESET_ALL}")
    print(f"{Fore.WHITE}Competitors:{Style.RESET_ALL}")
    for llm_id, config in llm_configs.items():
        print(f" - {Fore.GREEN}{llm_id}{Style.RESET_ALL}: {config['model_name']} ({config['model_provider']})")
    print(f"{Fore.WHITE}Tickers: {Fore.YELLOW}{', '.join(inputs.tickers)}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}Period: {Fore.YELLOW}{inputs.start_date}{Style.RESET_ALL} to {Fore.YELLOW}{inputs.end_date}{Style.RESET_ALL}\n")

    # Create and run the backtester
    backtester = BacktestEngine(
        agent=run_hedge_fund,
        tickers=inputs.tickers,
        start_date=inputs.start_date,
        end_date=inputs.end_date,
        initial_capital=inputs.initial_cash,
        llm_configs=llm_configs,
        selected_analysts=inputs.selected_analysts,
        initial_margin_requirement=inputs.margin_requirement,
    )

    try:
        backtester.run_backtest()
        print(f"\n{Fore.GREEN}Alpha Chaser completed successfully!{Style.RESET_ALL}")
    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}Alpha Chaser interrupted by user.{Style.RESET_ALL}")
        sys.exit(0)

if __name__ == "__main__":
    run_alpha_chaser()

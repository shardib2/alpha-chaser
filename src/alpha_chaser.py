import sys
from colorama import Fore, Style
from src.main import run_hedge_fund
from src.backtesting.engine import BacktestEngine
from src.cli.input import parse_cli_inputs
from src.llm.models import ModelProvider, get_model, get_model_info


def validate_roster(llm_configs: dict) -> None:
    """Fail fast, before any data fetching or LLM spend, if a competitor can't run."""
    problems = []
    for llm_id, config in llm_configs.items():
        name, provider = config["model_name"], config["model_provider"]
        try:
            provider_enum = ModelProvider(provider)
        except ValueError:
            problems.append(f"{llm_id}: unknown provider '{provider}'")
            continue
        if get_model_info(name, provider) is None:
            print(f"{Fore.YELLOW}Warning: {llm_id} model '{name}' is not in api_models.json; "
                  f"cost tracking will show $0 for it.{Style.RESET_ALL}")
        try:
            get_model(name, provider_enum)  # no network call; raises if key/routing missing
        except Exception as e:
            problems.append(f"{llm_id} ({name}): {e}")
    if problems:
        print(f"\n{Fore.RED}{Style.BRIGHT}Cannot start Alpha Chaser — fix these first:{Style.RESET_ALL}")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)


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
        "GPT_Standard": {"model_name": "gpt-5.5", "model_provider": "OpenAI"},
        "DeepSeek_Challenger": {"model_name": "deepseek-v4-pro", "model_provider": "DeepSeek"},
        "User_Selection": {"model_name": inputs.model_name, "model_provider": inputs.model_provider},
    }
    # Drop duplicates if the user picked a model already in the roster
    seen = set()
    for llm_id in list(llm_configs):
        key = (llm_configs[llm_id]["model_name"], llm_configs[llm_id]["model_provider"])
        if key in seen:
            del llm_configs[llm_id]
        else:
            seen.add(key)

    validate_roster(llm_configs)

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

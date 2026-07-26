"""Helper functions for LLM"""

import json
from pydantic import BaseModel
from src.llm.models import get_model, get_model_info
from src.utils.progress import progress
from src.graph.state import AgentState


# Token pricing per 1M tokens (Input, Output) — sourced from provider pricing pages, July 2026
MODEL_PRICES = {
    # Anthropic
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-4-8": (15.0, 75.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-7-sonnet": (3.0, 15.0),
    # OpenAI
    "gpt-5.5": (5.0, 30.0),
    "gpt-5.5-pro": (30.0, 180.0),
    "gpt-4o": (2.50, 10.0),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.40, 1.60),
    # Google
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-3.1-pro-preview": (2.50, 15.0),
    "gemini-2.0-flash": (0.10, 0.40),
    # xAI
    "grok-4.3": (1.25, 2.50),
    "grok-4": (3.0, 15.0),
    "grok-3": (3.0, 15.0),
    # Meta (via Together/Groq/DeepInfra)
    "meta-llama/llama-4-maverick": (0.15, 0.60),
    "meta-llama/llama-4-scout": (0.10, 0.30),
    "meta-llama/llama-3.3-70b-instruct": (0.59, 0.79),
    # DeepSeek
    "deepseek-v4-pro": (1.74, 3.48),
    "deepseek-v4-flash": (0.14, 0.28),
    "deepseek-chat": (0.14, 0.28),
    # Kimi
    "kimi-k2.6": (0.60, 2.50),
}

def call_llm(
    prompt: any,
    pydantic_model: type[BaseModel],
    agent_name: str | None = None,
    state: AgentState | None = None,
    max_retries: int = 3,
    default_factory=None,
) -> BaseModel:
    """
    Makes an LLM call with retry logic, handling both JSON supported and non-JSON supported models.

    Args:
        prompt: The prompt to send to the LLM
        pydantic_model: The Pydantic model class to structure the output
        agent_name: Optional name of the agent for progress updates and model config extraction
        state: Optional state object to extract agent-specific model configuration
        max_retries: Maximum number of retries (default: 3)
        default_factory: Optional factory function to create default response on failure

    Returns:
        An instance of the specified Pydantic model
    """
    
    # Extract model configuration if state is provided and agent_name is available
    if state and agent_name:
        model_name, model_provider = get_agent_model_config(state, agent_name)
    else:
        # Use system defaults when no state or agent_name is provided
        model_name = "gpt-4.1"
        model_provider = "OPENAI"

    # Extract API keys from state if available
    api_keys = None
    if state:
        api_keys = state.get("metadata", {}).get("api_keys")

    model_info = get_model_info(model_name, model_provider)
    try:
        llm = get_model(model_name, model_provider, api_keys)
    except Exception as e:
        # A missing key or unroutable provider should degrade this agent to its
        # default output, not crash the whole run.
        print(f"Error creating LLM client for {model_name} ({model_provider}): {e}")
        if default_factory:
            return default_factory()
        return create_default_response(pydantic_model)

    # For non-JSON support models, we can use structured output.
    # include_raw=True keeps the raw AIMessage so token usage stays available.
    use_structured = not (model_info and not model_info.has_json_mode())
    if use_structured:
        llm = llm.with_structured_output(
            pydantic_model,
            method="json_mode",
            include_raw=True,
        )

    # Call the LLM with retries
    for attempt in range(max_retries):
        try:
            # Call the LLM
            result = llm.invoke(prompt)

            if use_structured:
                raw_message = result.get("raw")
                parsed = result.get("parsed")
                if parsed is None:
                    raise ValueError(f"structured output parsing failed: {result.get('parsing_error')}")
            else:
                raw_message = result
                parsed = None

            # Alpha Chaser: Track costs if state and model info are available
            if state and model_info:
                llm_id = agent_name if agent_name else "default"
                # If agent_name is a specific portfolio manager, use its ID
                if llm_id.startswith("portfolio_manager_"):
                    llm_id = llm_id.replace("portfolio_manager_", "")
                
                # Extract token usage from the raw message (standard in LangChain)
                usage = getattr(raw_message, "usage_metadata", None) or \
                    (getattr(raw_message, "response_metadata", {}) or {}).get("token_usage", {})
                if usage:
                    in_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
                    out_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
                    
                    # Calculate cost
                    prices = MODEL_PRICES.get(model_info.model_name, (0.0, 0.0))
                    cost = (in_tokens / 1_000_000 * prices[0]) + (out_tokens / 1_000_000 * prices[1])
                    
                    # Store in state
                    if "metadata" not in state:
                        state["metadata"] = {}
                    if "llm_costs" not in state["metadata"]:
                        state["metadata"]["llm_costs"] = {}
                    
                    current_costs = state["metadata"]["llm_costs"].get(llm_id, {"input_tokens": 0, "output_tokens": 0, "total_cost": 0.0})
                    current_costs["input_tokens"] += in_tokens
                    current_costs["output_tokens"] += out_tokens
                    current_costs["total_cost"] += cost
                    state["metadata"]["llm_costs"][llm_id] = current_costs

            # For non-JSON support models, we need to extract and parse the JSON manually
            if not use_structured:
                parsed_result = extract_json_from_response(raw_message.content)
                if parsed_result:
                    return pydantic_model(**parsed_result)
                raise ValueError("could not extract JSON from model response")
            return parsed

        except Exception as e:
            if agent_name:
                progress.update_status(agent_name, None, f"Error - retry {attempt + 1}/{max_retries}")

            if attempt == max_retries - 1:
                print(f"Error in LLM call after {max_retries} attempts: {e}")
                # Use default_factory if provided, otherwise create a basic default
                if default_factory:
                    return default_factory()
                return create_default_response(pydantic_model)

    # This should never be reached due to the retry logic above
    return create_default_response(pydantic_model)


def create_default_response(model_class: type[BaseModel]) -> BaseModel:
    """Creates a safe default response based on the model's fields."""
    default_values = {}
    for field_name, field in model_class.model_fields.items():
        if field.annotation == str:
            default_values[field_name] = "Error in analysis, using default"
        elif field.annotation == float:
            default_values[field_name] = 0.0
        elif field.annotation == int:
            default_values[field_name] = 0
        elif hasattr(field.annotation, "__origin__") and field.annotation.__origin__ == dict:
            default_values[field_name] = {}
        else:
            # For other types (like Literal), try to use the first allowed value
            if hasattr(field.annotation, "__args__"):
                default_values[field_name] = field.annotation.__args__[0]
            else:
                default_values[field_name] = None

    return model_class(**default_values)


def extract_json_from_response(content) -> dict | None:
    """Extracts JSON from a response, handling markdown-wrapped and raw JSON formats."""
    try:
        # Reasoning models (e.g. Anthropic extended thinking) return content as a
        # list of blocks (thinking + text). Concatenate the text blocks.
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            content = "\n".join(parts)
        # 1. Try markdown code block with ```json
        json_start = content.find("```json")
        if json_start != -1:
            json_text = content[json_start + 7:]  # Skip past ```json
            json_end = json_text.find("```")
            if json_end != -1:
                json_text = json_text[:json_end].strip()
                try:
                    return json.loads(json_text)
                except json.JSONDecodeError:
                    pass

        # 2. Try markdown code block without json specifier
        json_start = content.find("```")
        if json_start != -1:
            json_text = content[json_start + 3:]
            json_end = json_text.find("```")
            if json_end != -1:
                json_text = json_text[:json_end].strip()
                try:
                    return json.loads(json_text)
                except json.JSONDecodeError:
                    pass

        # 3. Try to parse the entire content as JSON
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            pass

        # 4. Find the first top-level JSON object by matching braces
        brace_start = content.find("{")
        if brace_start != -1:
            depth = 0
            for i, char in enumerate(content[brace_start:], brace_start):
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(content[brace_start:i + 1])
                        except json.JSONDecodeError:
                            break

    except Exception as e:
        print(f"Error extracting JSON from response: {e}")
    return None


def get_agent_model_config(state, agent_name):
    """
    Get model configuration for a specific agent from the state.
    Falls back to global model configuration if agent-specific config is not available.
    Always returns valid model_name and model_provider values.
    """
    request = state.get("metadata", {}).get("request")
    
    if request and hasattr(request, 'get_agent_model_config'):
        # Get agent-specific model configuration
        model_name, model_provider = request.get_agent_model_config(agent_name)
        # Ensure we have valid values
        if model_name and model_provider:
            return model_name, model_provider.value if hasattr(model_provider, 'value') else str(model_provider)
    
    # Fall back to global configuration (system defaults)
    model_name = state.get("metadata", {}).get("model_name") or "gpt-4.1"
    model_provider = state.get("metadata", {}).get("model_provider") or "OPENAI"
    
    # Convert enum to string if necessary
    if hasattr(model_provider, 'value'):
        model_provider = model_provider.value
    
    return model_name, model_provider

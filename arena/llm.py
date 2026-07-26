"""LLM clients: one real client (OpenRouter) covering every model, plus a fake for dry runs.

OpenRouter is used because a single API key routes to GPT, Claude, Gemini,
DeepSeek, Grok, Llama, Qwen, etc. Set OPENROUTER_API_KEY in the environment.
"""

import json
import logging
import os
import time

import requests

log = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of an LLM reply (fenced or bare)."""
    text = text.strip()
    if "```" in text:
        for chunk in text.split("```"):
            chunk = chunk.strip()
            if chunk.startswith("json"):
                chunk = chunk[4:].strip()
            if chunk.startswith("{"):
                text = chunk
                break
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in response")
    depth = 0
    in_str = False
    escape = False
    for i, ch in enumerate(text[start:], start):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
        elif ch == '"' and not escape:
            in_str = not in_str
        elif not in_str:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start : i + 1])
    raise ValueError("unbalanced JSON object in response")


class OpenRouterClient:
    def __init__(self, api_key: str | None = None, max_retries: int = 3, timeout: int = 180):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Create a key at https://openrouter.ai/keys "
                "and export it (or add it as a GitHub Actions secret)."
            )
        self.max_retries = max_retries
        self.timeout = timeout
        self._session = requests.Session()

    def decide(self, model: str, system_prompt: str, user_prompt: str) -> tuple[dict, dict]:
        """Returns (parsed_decision_json, usage_dict). Raises after exhausting retries."""
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.5,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/shardib2/alpha-chaser",
            "X-Title": "LLM Trading Arena",
        }
        last_err: Exception = RuntimeError("no attempts made")
        for attempt in range(self.max_retries):
            try:
                resp = self._session.post(OPENROUTER_URL, json=payload, headers=headers, timeout=self.timeout)
                if resp.status_code in (429, 500, 502, 503):
                    raise RuntimeError(f"retryable HTTP {resp.status_code}: {resp.text[:200]}")
                resp.raise_for_status()
                body = resp.json()
                if "error" in body:
                    raise RuntimeError(f"OpenRouter error: {body['error']}")
                content = body["choices"][0]["message"]["content"]
                usage = body.get("usage", {}) or {}
                return extract_json(content), usage
            except Exception as e:  # noqa: BLE001
                last_err = e
                wait = 2 ** (attempt + 1)
                log.warning("%s attempt %d failed (%s); retrying in %ss", model, attempt + 1, e, wait)
                time.sleep(wait)
        raise RuntimeError(f"{model}: all {self.max_retries} attempts failed: {last_err}")


class FakeLLM:
    """Deterministic offline stand-in for --dry-run and tests.

    Each competitor buys the strongest 1-month performer it doesn't own yet
    (offset by a per-model index so they don't all pick the same name) and
    sells any position down more than 5% from cost.
    """

    def __init__(self):
        self._model_index: dict[str, int] = {}

    def decide(self, model: str, system_prompt: str, user_prompt: str) -> tuple[dict, dict]:
        ctx = extract_json(user_prompt)
        snapshot = ctx.get("market_snapshot", {})
        portfolio = ctx.get("your_portfolio", {})
        positions = portfolio.get("positions", {})
        cash = portfolio.get("cash", 0.0)

        idx = self._model_index.setdefault(model, len(self._model_index))
        ranked = sorted(
            ((t, d) for t, d in snapshot.items() if d.get("chg_1mo_pct") is not None),
            key=lambda kv: kv[1]["chg_1mo_pct"],
            reverse=True,
        )
        orders = []
        for ticker, pos in positions.items():
            info = snapshot.get(ticker)
            if info and pos.get("avg_cost") and info["price"] < pos["avg_cost"] * 0.95:
                orders.append(
                    {"action": "sell", "ticker": ticker, "quantity": pos["shares"],
                     "reasoning": "Stop loss: down >5% from cost."}
                )
        candidates = [t for t, _ in ranked if t not in positions]
        if candidates and cash > 1000:
            pick = candidates[idx % len(candidates)]
            price = snapshot[pick]["price"]
            qty = int((cash * 0.25) // price)
            if qty > 0:
                orders.append(
                    {"action": "buy", "ticker": pick, "quantity": qty,
                     "reasoning": "Deterministic dry-run pick: strong 1-month momentum."}
                )
        return (
            {"orders": orders, "market_view": "Dry-run deterministic decision."},
            {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200},
        )

"""Offline cost scenarios using the bundled LiteLLM price map and scripted usage."""

from __future__ import annotations

import math

import litellm

from .evaluation_dataset import load_dataset


def price_for(model: str, prices: dict) -> dict | None:
    """Look up an exact model or its unambiguous provider-qualified alias."""
    if model.startswith(("ollama/", "ollama_chat/")):
        return {
            "litellm_provider": model.partition("/")[0],
            "input_cost_per_token": 0,
            "output_cost_per_token": 0,
        }
    if model.startswith("vertex_ai/") and prices is litellm.model_cost:
        from litellm.utils import get_model_info_helper

        try:
            info = get_model_info_helper(model, catalog_only=True, preserve_unset_costs=True)
            return prices.get(info["key"])
        except Exception:
            return None
    if model in prices:
        return prices[model]
    provider, sep, name = model.partition("/")
    entry = prices.get(name) if sep else None
    if isinstance(entry, dict) and entry.get("litellm_provider") == provider:
        return entry
    return None


def call_cost(usage: dict, price: dict | None) -> float | None:
    """Price input (including cache reads/writes) and output, or return unknown."""
    if not isinstance(price, dict):
        return None
    counts = [usage.get(key) for key in ("input", "output", "cached", "write")]
    if any(type(n) is not int or n < 0 for n in counts):
        return None
    input_tokens, output_tokens, cached, write = counts
    if cached + write > input_tokens:
        return None
    components = [
        (input_tokens - cached - write, "input_cost_per_token"),
        (output_tokens, "output_cost_per_token"),
        (cached, "cache_read_input_token_cost"),
        (write, "cache_creation_input_token_cost"),
    ]
    total = 0.0
    for count, key in components:
        if not count:
            continue
        rate = price.get(key)
        if not isinstance(rate, (int, float)) or isinstance(rate, bool):
            return None
        if (
            not math.isfinite(rate)
            or rate < 0
            or (rate == 0 and price.get("litellm_provider") not in ("ollama", "ollama_chat"))
        ):
            return None
        total += count * rate
    return total


def scripted_costs(settings, *, prices=None, dataset=None):
    """Estimate four explicitly hypothetical ten-call scenarios per dataset incident.

    Each role has a 4096-token stable prefix. Cache reads start on that role's
    second call; a write is charged when the model map has a creation price.
    Token counts and routing are deliberately fixed across cases and tiers.
    """
    prices = litellm.model_cost if prices is None else prices
    dataset = load_dataset() if dataset is None else dataset
    main = settings.models[0]
    fast = (settings.fast_models or settings.models)[0]
    roles = ("coordinator", "metrics", "logs", "metrics", "logs") + ("coordinator",) * 5
    rows = []
    for case in dataset["incidents"]:
        scenarios = {}
        reasons = {}
        notes = set()
        for fast_enabled in (False, True):
            for cache_enabled in (False, True):
                cache = "on" if cache_enabled else "off"
                tier = "on" if fast_enabled else "off"
                key = f"cache_{cache}_fast_{tier}"
                if fast_enabled and fast == main:
                    scenarios[key] = None
                    reasons[key] = "no distinct fast tier"
                    continue
                total = 0.0
                seen = set()
                known = True
                for turn, role in enumerate(roles):
                    model = fast if fast_enabled and role != "coordinator" else main
                    price = price_for(model, prices)
                    eligible = model.startswith(("anthropic/", "openai/", "gemini/"))
                    if cache_enabled and not eligible:
                        notes.add(f"Cache not simulated for {model}")
                    if (
                        cache_enabled
                        and eligible
                        and price is not None
                        and "supports_prompt_caching" not in price
                    ):
                        known = False
                    caching = (
                        cache_enabled
                        and eligible
                        and price is not None
                        and price.get("supports_prompt_caching")
                    )
                    first = (role, model) not in seen
                    if (
                        caching
                        and first
                        and model.startswith("anthropic/")
                        and "cache_creation_input_token_cost" not in price
                    ):
                        known = False
                    cached = 4096 if caching and not first else 0
                    write = (
                        4096
                        if caching
                        and first
                        and model.startswith("anthropic/")
                        and "cache_creation_input_token_cost" in price
                        else 0
                    )
                    seen.add((role, model))
                    usage = {
                        "input": 6000 + turn * 200,
                        "output": 150,
                        "cached": cached,
                        "write": write,
                    }
                    amount = call_cost(usage, price)
                    if amount is None:
                        known = False
                    else:
                        total += amount
                scenarios[key] = total if known else None
        rows.append(
            {"incident": case["id"], **scenarios, "reasons": reasons, "notes": sorted(notes)}
        )
    return rows

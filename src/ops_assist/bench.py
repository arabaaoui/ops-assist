"""Measure streamed text generation without treating chunks as tokens."""

import os
import statistics
import time
from urllib.parse import urlsplit

import litellm

from .config import check_profile_env
from .doctor import Probes, _ollama_models


def benchmark(
    settings,
    prompt,
    runs,
    *,
    allow_remote=False,
    ollama=False,
    clock=None,
    completion=None,
    probes=None,
):
    """Run sequential generations and return timing statistics and optional memory."""
    if not 1 <= runs <= 100:
        raise ValueError("runs must be between 1 and 100")
    if not prompt.strip() or len(prompt.encode("utf-8")) > 65536:
        raise ValueError("prompt must be nonempty and at most 65536 bytes")
    model = settings.models[0]
    base = settings.api_base
    local_model = model.startswith(("ollama/", "ollama_chat/"))
    local_base = not base or urlsplit(base).hostname in ("localhost", "127.0.0.1", "::1")
    if not allow_remote and (settings.profile != "local" or not local_model or not local_base):
        raise ValueError("remote profile, model or endpoint requires --allow-remote")
    check_profile_env(settings, dict(os.environ))
    clock = clock or time.perf_counter
    completion = completion or litellm.completion
    samples = []
    for _ in range(runs):
        start = clock()
        kwargs = {"api_base": base} if base else {}
        try:
            stream = completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                stream_options={"include_usage": True},
                max_tokens=512,
                **kwargs,
            )
            first = last = None
            tokens = None
            for chunk in stream:
                now = clock()
                choices = chunk.choices or []
                if choices and getattr(choices[0].delta, "content", None):
                    if first is None:
                        first = now
                    last = now
                usage = getattr(chunk, "usage", None)
                count = getattr(usage, "completion_tokens", None)
                if type(count) is int and count > 0:
                    tokens = count
            end = clock()
        except Exception as exc:
            raise ValueError(f"benchmark generation failed ({type(exc).__name__})") from exc
        if first is None:
            raise ValueError("generation returned no visible text")
        decode = last - first
        # The first token arrives at TTFT; the remaining tokens span the decode interval.
        rate = (tokens - 1) / decode if tokens and tokens > 1 and decode > 0 else None
        samples.append(
            {
                "ttft_seconds": first - start,
                "decode_tokens_per_second": rate,
                "total_seconds": end - start,
                "output_tokens": tokens,
            }
        )
    summary = {}
    for key in ("ttft_seconds", "decode_tokens_per_second", "total_seconds"):
        values = [sample[key] for sample in samples if sample[key] is not None]
        summary[key] = (
            {
                "median": statistics.median(values),
                "min": min(values),
                "max": max(values),
                "samples": len(values),
            }
            if values
            else None
        )
    memory = None
    if ollama and local_model:
        try:
            name = model.split("/", 1)[1]
            memory = next(
                (
                    item
                    for item in _ollama_models(probes or Probes())
                    if item["name"] == name or item["name"] == name + ":latest"
                ),
                None,
            )
        except Exception:
            pass
    return {
        "profile": settings.profile,
        "model": model,
        "runs": samples,
        "summary": summary,
        "ollama_memory": memory,
    }

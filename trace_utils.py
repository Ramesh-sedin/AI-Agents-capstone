"""Structured JSON run tracing and API-free trace viewing helpers."""

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

BASE_DIR = Path(__file__).resolve().parent
TRACES_DIR = BASE_DIR / "traces"


def new_run_trace(goal: str, model: str = "gemini-3.5-flash") -> dict:
    """Create the stable envelope written once when a live agent run finishes."""
    return {
        "run_id": uuid.uuid4().hex,
        "goal": goal,
        "model": model,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None,
        "duration_ms": 0,
        "iterations": [],
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
        "stop_reason": None,
        "final_answer": None,
        "_started_monotonic": time.monotonic(),
    }


def finish_run_trace(trace: dict, stop_reason: str, final_answer: str) -> dict:
    """Finalize totals and remove the private timing field before JSON serialization."""
    elapsed = time.monotonic() - trace.pop("_started_monotonic", time.monotonic())
    trace["ended_at"] = datetime.now(timezone.utc).isoformat()
    trace["duration_ms"] = round(elapsed * 1000, 3)
    trace["stop_reason"] = stop_reason
    trace["final_answer"] = final_answer

    cost_per_million = float(os.getenv("ESTIMATED_COST_PER_MILLION_TOKENS", "0"))
    trace["estimated_cost_usd"] = round(
        trace["total_tokens"] * cost_per_million / 1_000_000,
        6,
    )
    return trace


def add_iteration(
    trace: dict,
    iteration: int,
    elapsed_ms: float,
    tokens_used: int,
    cumulative_tokens: int,
    tool_requests: Iterable[dict],
    tool_results: Iterable[dict],
    final_text: str | None = None,
) -> None:
    """Append one complete iteration; elapsed_ms is measured at the iteration boundary."""
    trace["iterations"].append({
        "iteration": iteration,
        "elapsed_ms": round(elapsed_ms, 3),
        "tokens_used": tokens_used,
        "cumulative_tokens": cumulative_tokens,
        "tool_requested": list(tool_requests),
        "tool_result": list(tool_results),
        "final_text": final_text,
    })
    trace["total_tokens"] = cumulative_tokens


def write_run_trace(trace: dict, directory: Path | None = None) -> Path:
    """Write one JSON object for one run to traces/run_<id>.json."""
    target_dir = directory or TRACES_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"run_{trace['run_id']}.json"
    path.write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def read_run_trace(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "iterations" not in data:
        raise ValueError("Trace must be a JSON object containing an 'iterations' list")
    return data

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Callable

from .derivatives import build_recommendation, collect_option_chain
from .market_data import collect_overview, session_state
from .sectors import collect_sectors
from .storage import init_storage, persist_cycle, redis_client

LOCK_KEY = "marketpulse:collector:lock"
LOCK_TTL_SECONDS = 90
LOOP_SECONDS = 60
OPTIONS_EVERY_CYCLES = 5


def current_cycle_is_relevant() -> bool:
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return False
    sessions = [
        ("Asia/Kolkata", 9, 15, 15, 30),
        ("America/New_York", 9, 30, 16, 0),
        ("Europe/London", 8, 0, 16, 30),
        ("Asia/Tokyo", 9, 0, 15, 30),
        ("Australia/Sydney", 10, 0, 16, 0),
        ("Asia/Shanghai", 9, 30, 15, 0),
        ("Asia/Singapore", 9, 0, 17, 0),
    ]
    return any(session_state(*session)[0] == "active" for session in sessions)


def with_retries(function: Callable[[], Any], attempts: int = 3) -> Any:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return function()
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(2**attempt)
    raise last_error or RuntimeError("collector failed")


def run_cycle(cycle_number: int) -> None:
    client = redis_client()
    lock_token = f"{datetime.now(timezone.utc).isoformat()}:{cycle_number}"
    if not client.set(LOCK_KEY, lock_token, nx=True, ex=LOCK_TTL_SECONDS):
        return
    try:
        overview = with_retries(collect_overview)
        sectors = with_retries(collect_sectors)
        options = collect_option_chain() if cycle_number % OPTIONS_EVERY_CYCLES == 0 else {}
        recommendation = build_recommendation(overview, options or {"signal": "UNAVAILABLE"})
        persist_cycle(overview, sectors, options, recommendation, persist_options=bool(options))
        client.setex("marketpulse:latest:sectors", 600, json.dumps(sectors))
        if options:
            client.setex("marketpulse:latest:options:NIFTY", 600, json.dumps(options))
        client.setex("marketpulse:latest:recommendation:NIFTY", 600, json.dumps(recommendation))
        client.setex("marketpulse:collector:last_success", 600, overview["as_of"])
        client.setex(
            f"marketpulse:collector:run:{cycle_number}",
            600,
            json.dumps({"as_of": overview["as_of"], "options_collected": bool(options), "status": "success"}),
        )
    finally:
        current = client.get(LOCK_KEY)
        if current == lock_token:
            client.delete(LOCK_KEY)


def main() -> None:
    with_retries(init_storage)
    cycle_number = 0
    while True:
        cycle_number += 1
        if current_cycle_is_relevant():
            try:
                run_cycle(cycle_number)
            except Exception as exc:
                redis_client().setex(
                    "marketpulse:collector:last_error",
                    600,
                    json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "error": str(exc)}),
                )
        time.sleep(LOOP_SECONDS)


if __name__ == "__main__":
    main()

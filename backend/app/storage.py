from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import redis
from psycopg import connect
from psycopg.rows import dict_row


def postgres_connection():
    return connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "marketpulse"),
        user=os.getenv("POSTGRES_USER", "marketpulse"),
        password=os.getenv("POSTGRES_PASSWORD", "marketpulse_dev_password"),
        row_factory=dict_row,
    )


def redis_client():
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        decode_responses=True,
    )


def init_storage() -> None:
    with postgres_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS market_history (
                id BIGSERIAL PRIMARY KEY,
                observed_at TIMESTAMPTZ NOT NULL,
                signal TEXT NOT NULL,
                score INTEGER NOT NULL,
                confidence TEXT NOT NULL,
                overview JSONB NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS market_snapshots (
                id BIGSERIAL PRIMARY KEY,
                instrument TEXT NOT NULL,
                observed_at TIMESTAMPTZ NOT NULL,
                open_value DOUBLE PRECISION,
                high_value DOUBLE PRECISION,
                low_value DOUBLE PRECISION,
                close_value DOUBLE PRECISION,
                change_percent DOUBLE PRECISION,
                source TEXT NOT NULL,
                freshness TEXT NOT NULL,
                UNIQUE (instrument, observed_at, source)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sector_snapshots (
                id BIGSERIAL PRIMARY KEY,
                sector TEXT NOT NULL,
                index_name TEXT NOT NULL,
                observed_at TIMESTAMPTZ NOT NULL,
                value DOUBLE PRECISION,
                change_percent DOUBLE PRECISION,
                relative_strength DOUBLE PRECISION,
                score INTEGER,
                trend_score INTEGER,
                momentum_score INTEGER,
                breadth_score INTEGER,
                source TEXT NOT NULL,
                freshness TEXT NOT NULL,
                UNIQUE (sector, observed_at, source)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS options_snapshots (
                id BIGSERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                expiry TEXT NOT NULL,
                observed_at TIMESTAMPTZ NOT NULL,
                underlying_value DOUBLE PRECISION,
                pcr DOUBLE PRECISION,
                atm_iv DOUBLE PRECISION,
                max_pain DOUBLE PRECISION,
                support DOUBLE PRECISION,
                resistance DOUBLE PRECISION,
                call_oi DOUBLE PRECISION,
                put_oi DOUBLE PRECISION,
                call_change_oi DOUBLE PRECISION,
                put_change_oi DOUBLE PRECISION,
                source TEXT NOT NULL,
                freshness TEXT NOT NULL,
                UNIQUE (symbol, expiry, observed_at, source)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS recommendation_snapshots (
                id BIGSERIAL PRIMARY KEY,
                observed_at TIMESTAMPTZ NOT NULL,
                engine_version TEXT NOT NULL,
                market_score INTEGER,
                sector_score INTEGER,
                derivatives_signal TEXT,
                bias TEXT NOT NULL,
                setups JSONB NOT NULL,
                input_snapshot_ids JSONB NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sector_constituents (
                id BIGSERIAL PRIMARY KEY,
                sector TEXT NOT NULL,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                weight DOUBLE PRECISION,
                valid_from DATE NOT NULL,
                valid_to DATE,
                UNIQUE (sector, exchange, symbol, valid_from)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS constituent_snapshots (
                id BIGSERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                observed_at TIMESTAMPTZ NOT NULL,
                price DOUBLE PRECISION,
                volume DOUBLE PRECISION,
                change_percent DOUBLE PRECISION,
                rsi DOUBLE PRECISION,
                ema20 DOUBLE PRECISION,
                ema50 DOUBLE PRECISION,
                ema200 DOUBLE PRECISION,
                source TEXT NOT NULL,
                freshness TEXT NOT NULL,
                UNIQUE (symbol, observed_at, source)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sector_rotation (
                id BIGSERIAL PRIMARY KEY,
                observed_at TIMESTAMPTZ NOT NULL,
                sector TEXT NOT NULL,
                relative_strength DOUBLE PRECISION,
                momentum DOUBLE PRECISION,
                quadrant TEXT NOT NULL,
                score INTEGER,
                UNIQUE (sector, observed_at)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS market_history_observed_at_idx
            ON market_history (observed_at DESC)
            """
        )


def persist_overview(overview: dict[str, Any]) -> None:
    payload = json.dumps(overview)
    try:
        client = redis_client()
        client.setex("marketpulse:latest", 300, payload)
        client.rpush("marketpulse:history", payload)
        client.ltrim("marketpulse:history", -240, -1)
    except Exception:
        pass


def _number(value: Any) -> float | None:
    return float(value) if value is not None else None


def persist_cycle(
    overview: dict[str, Any],
    sectors: dict[str, Any],
    options: dict[str, Any],
    recommendation: dict[str, Any],
    persist_options: bool = True,
) -> None:
    observed_at = overview["as_of"]
    persist_overview(overview)
    try:
        with postgres_connection() as connection:
            for quote in overview.get("global_exchanges", []) + [
                overview.get("nifty50"), overview.get("bank_nifty"), overview.get("india_vix")
            ]:
                if not quote or not quote.get("timestamp"):
                    continue
                connection.execute(
                    """
                    INSERT INTO market_snapshots
                    (instrument, observed_at, open_value, high_value, low_value, close_value,
                     change_percent, source, freshness)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (quote["symbol"], quote["timestamp"], quote.get("value"), quote.get("value"), quote.get("value"), quote.get("value"), quote.get("change_percent"), quote.get("source", "Unavailable"), quote.get("freshness", "unavailable")),
                )
            for item in sectors.get("items", []):
                if not item.get("timestamp"):
                    continue
                connection.execute(
                    """
                    INSERT INTO sector_snapshots
                    (sector, index_name, observed_at, value, change_percent, relative_strength,
                     score, trend_score, momentum_score, breadth_score, source, freshness)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (item["sector"], item["index_name"], item["timestamp"], item.get("value"), item.get("change_percent"), item.get("relative_strength"), item.get("score"), item.get("trend_score"), item.get("momentum_score"), item.get("breadth_score"), item.get("source", "Unavailable"), item.get("freshness", "unavailable")),
                )
                connection.execute(
                    """
                    INSERT INTO sector_rotation (observed_at, sector, relative_strength, momentum, quadrant, score)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (item["timestamp"], item["sector"], item.get("relative_strength"), item.get("momentum_score"), item.get("classification", "UNAVAILABLE"), item.get("score")),
                )
            if persist_options and options.get("expiry") and options.get("timestamp"):
                totals = options.get("totals", {})
                connection.execute(
                    """
                    INSERT INTO options_snapshots
                    (symbol, expiry, observed_at, underlying_value, pcr, atm_iv, max_pain,
                     support, resistance, call_oi, put_oi, call_change_oi, put_change_oi,
                     source, freshness)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (options["symbol"], options["expiry"], options["timestamp"], options.get("underlying_value"), options.get("pcr"), _number((options.get("atm_iv") or {}).get("call")), options.get("max_pain"), options.get("support"), options.get("resistance"), totals.get("call_oi"), totals.get("put_oi"), totals.get("call_change_oi"), totals.get("put_change_oi"), options.get("source", "Unavailable"), options.get("freshness", "unavailable")),
                )
            connection.execute(
                """
                INSERT INTO recommendation_snapshots
                (observed_at, engine_version, market_score, sector_score, derivatives_signal,
                 bias, setups, input_snapshot_ids)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                """,
                (observed_at, "0.5.0", recommendation.get("market_score"), None, recommendation.get("derivatives_signal"), recommendation.get("bias", "NEUTRAL"), json.dumps(recommendation.get("setups", [])), json.dumps({"overview_as_of": observed_at, "options_timestamp": options.get("timestamp")})),
            )
    except Exception:
        pass


def cached_json(key: str) -> dict[str, Any] | None:
    try:
        value = redis_client().get(key)
        return json.loads(value) if value else None
    except Exception:
        return None


def cached_history() -> list[dict[str, Any]]:
    try:
        return [json.loads(value) for value in redis_client().lrange("marketpulse:history", 0, -1)]
    except Exception:
        return []


def latest_overview() -> dict[str, Any] | None:
    cached = cached_json("marketpulse:latest")
    if cached:
        return cached
    try:
        with postgres_connection() as connection:
            row = connection.execute(
                "SELECT overview FROM market_history ORDER BY observed_at DESC LIMIT 1"
            ).fetchone()
        return row["overview"] if row else None
    except Exception:
        return None

    try:
        with postgres_connection() as connection:
            connection.execute(
                """
                INSERT INTO market_history (observed_at, signal, score, confidence, overview)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                """,
                (
                    overview["as_of"],
                    overview["overall_signal"],
                    overview["score"],
                    overview["confidence"],
                    payload,
                ),
            )
    except Exception:
        pass


def read_history(limit: int = 24) -> list[dict[str, Any]]:
    try:
        with postgres_connection() as connection:
            rows = connection.execute(
                """
                SELECT observed_at, signal, score, confidence
                FROM market_history
                ORDER BY observed_at DESC
                LIMIT %s
                """,
                (min(max(limit, 1), 100),),
            ).fetchall()
        return [
            {
                "timestamp": row["observed_at"].isoformat(),
                "signal": row["signal"],
                "score": row["score"],
                "confidence": row["confidence"],
            }
            for row in rows
        ]
    except Exception:
        return []


def storage_health() -> dict[str, str]:
    result = {"redis": "unavailable", "postgres": "unavailable"}
    try:
        redis_client().ping()
        result["redis"] = "ready"
    except Exception:
        pass
    try:
        with postgres_connection() as connection:
            connection.execute("SELECT 1")
        result["postgres"] = "ready"
    except Exception:
        pass
    return result
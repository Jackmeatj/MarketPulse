from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from .stocks import SECTOR_STOCKS
from .storage import postgres_connection, redis_client

DEFAULT_LOOKBACK_DAYS = 365
NSE_SOURCE = "NSE India historical daily feed"


def _normalize_symbol(symbol: str) -> str:
    token = (symbol or "").upper().strip().replace(".NS", "")
    return token.replace("-", "")


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _canonical_symbols() -> list[str]:
    seen: set[str] = set()
    symbols: list[str] = []
    for bucket in SECTOR_STOCKS.values():
        for symbol in bucket:
            canonical = _normalize_symbol(symbol)
            if canonical and canonical not in seen:
                seen.add(canonical)
                symbols.append(canonical)
    return symbols


def canonical_symbols() -> list[str]:
    return _canonical_symbols()


def _row_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    return None


def _parse_date(raw: Any) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    try:
        text = str(raw).strip()
        if not text:
            return None
        # Common NSE variants: 2024-01-02, 02-Jan-2024, 02-Jan-2024
        for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return date.fromisoformat(text)
    except Exception:
        return None


def _numeric(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "--", "nan", "NaN"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def seed_instrument_master(symbols: Iterable[str] | None = None) -> int:
    source_symbols = list(symbols or _canonical_symbols())
    with postgres_connection() as connection:
        for symbol in source_symbols:
            canonical = _normalize_symbol(symbol)
            if not canonical:
                continue
            connection.execute(
                """
                INSERT INTO instruments
                (symbol, exchange, company_name, isin, sector, industry, active, source, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol) DO UPDATE SET
                    exchange = EXCLUDED.exchange,
                    company_name = EXCLUDED.company_name,
                    isin = EXCLUDED.isin,
                    sector = EXCLUDED.sector,
                    industry = EXCLUDED.industry,
                    active = EXCLUDED.active,
                    source = EXCLUDED.source,
                    updated_at = NOW()
                """,
                (
                    canonical,
                    "NSE",
                    canonical,
                    None,
                    None,
                    None,
                    True,
                    "seed",
                ),
            )
    return len(source_symbols)


def _fetch_daily_history_from_nse(symbol: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    try:
        from jugaad_data.nse import stock_df
    except Exception:
        return []

    try:
        frame = stock_df(symbol=symbol, from_date=start_date, to_date=end_date, series="EQ")
    except Exception:
        return []

    if frame is None or getattr(frame, "empty", True):
        return []

    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        date_value = _parse_date(_row_value(row.to_dict(), "DATE", "Date", "date"))
        if date_value is None:
            continue
        open_price = _numeric(_row_value(row.to_dict(), "OPEN", "Open", "open"))
        high_price = _numeric(_row_value(row.to_dict(), "HIGH", "High", "high"))
        low_price = _numeric(_row_value(row.to_dict(), "LOW", "Low", "low"))
        close_price = _numeric(_row_value(row.to_dict(), "CLOSE", "Close", "close"))
        volume_value = _numeric(_row_value(row.to_dict(), "VOLUME", "Volume", "volume", "TOTAL_TRADES"))
        rows.append(
            {
                "symbol": _normalize_symbol(symbol),
                "trade_date": date_value,
                "open_price": open_price,
                "high_price": high_price,
                "low_price": low_price,
                "close_price": close_price,
                "volume": int(volume_value) if volume_value is not None else None,
            }
        )
    return rows


def store_nse_daily_history(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    with postgres_connection() as connection:
        inserted = 0
        for row in rows:
            symbol = _normalize_symbol(row["symbol"])
            trade_date = row["trade_date"]
            open_value = row.get("open_price")
            high_value = row.get("high_price")
            low_value = row.get("low_price")
            close_value = row.get("close_price")
            volume_value = row.get("volume")
            connection.execute(
                """
                INSERT INTO nse_daily_prices
                (symbol, trade_date, open_price, high_price, low_price, close_price, volume, source, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol, trade_date, source) DO UPDATE SET
                    open_price = EXCLUDED.open_price,
                    high_price = EXCLUDED.high_price,
                    low_price = EXCLUDED.low_price,
                    close_price = EXCLUDED.close_price,
                    volume = EXCLUDED.volume,
                    created_at = NOW()
                """,
                (
                    symbol,
                    trade_date,
                    open_value,
                    high_value,
                    low_value,
                    close_value,
                    volume_value,
                    NSE_SOURCE,
                ),
            )
            inserted += 1
    return inserted


def sync_nse_market_data(force: bool = False) -> dict[str, Any]:
    cache_key = "marketpulse:nse:last_sync"
    now = datetime.now(timezone.utc)
    if not force:
        try:
            cached = redis_client().get(cache_key)
            if cached:
                last_sync = datetime.fromisoformat(cached)
                if (now - last_sync).total_seconds() < 60 * 60 * 6:
                    return {"status": "skipped", "reason": "recent sync already ran"}
        except Exception:
            pass

    symbols = _canonical_symbols()
    seed_instrument_master(symbols)

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    inserted = 0
    for symbol in symbols:
        rows = _fetch_daily_history_from_nse(symbol, start_date, end_date)
        inserted += store_nse_daily_history(rows)

    try:
        redis_client().setex(cache_key, 60 * 60 * 6, now.isoformat())
    except Exception:
        pass

    return {
        "status": "ok",
        "symbols": len(symbols),
        "inserted_rows": inserted,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }


def sync_nse_corporate_events(symbols: list[str] | None = None) -> int:
    from .nse_financial_ingest import fetch_nse_corporate_events, parse_corporate_events

    imported = 0
    for symbol in symbols or _canonical_symbols():
        try:
            imported += parse_corporate_events(symbol, fetch_nse_corporate_events(symbol))
        except Exception:
            continue
    return imported


def sync_nse_financial_results(symbols: list[str] | None = None) -> int:
    from .nse_financial_ingest import ingest_financial_results

    return ingest_financial_results(symbols or _canonical_symbols())["imported"]

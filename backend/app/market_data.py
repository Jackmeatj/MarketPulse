from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo

import httpx

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
NSE_INDICES_URL = "https://www.nseindia.com/api/allIndices"
NSE_FII_DII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
USER_AGENT = "Mozilla/5.0 (MarketPulse/0.3)"

YAHOO_SYMBOLS = {
    "NASDAQ": "^IXIC",
    "DOW": "^DJI",
    "INDIA VIX": "^INDIAVIX",
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
}

DISPLAY_NAMES = {
    "NASDAQ": "Nasdaq Composite",
    "DOW": "Dow Jones",
    "INDIA VIX": "India VIX",
    "NIFTY 50": "NIFTY 50",
    "BANK NIFTY": "BANK NIFTY",
}

MARKET_SESSIONS = {
    "NASDAQ": ("America/New_York", 9, 30, 16, 0),
    "DOW": ("America/New_York", 9, 30, 16, 0),
    "INDIA VIX": ("Asia/Kolkata", 9, 15, 15, 30),
    "NIFTY 50": ("Asia/Kolkata", 9, 15, 15, 30),
    "BANK NIFTY": ("Asia/Kolkata", 9, 15, 15, 30),
}

GLOBAL_SYMBOLS = {
    "S&P 500": ("^GSPC", "USA", "America/New_York", 9, 30, 16, 0),
    "NASDAQ": ("^IXIC", "USA", "America/New_York", 9, 30, 16, 0),
    "DOW JONES": ("^DJI", "USA", "America/New_York", 9, 30, 16, 0),
    "SHANGHAI": ("000001.SS", "China", "Asia/Shanghai", 9, 30, 15, 0),
    "HANG SENG": ("^HSI", "Hong Kong", "Asia/Hong_Kong", 9, 30, 16, 0),
    "NIKKEI 225": ("^N225", "Japan", "Asia/Tokyo", 9, 0, 15, 30),
    "ASX 200": ("^AXJO", "Australia", "Australia/Sydney", 10, 0, 16, 0),
    "DAX": ("^GDAXI", "Germany", "Europe/Berlin", 9, 0, 17, 30),
    "SINGAPORE": ("^STI", "Singapore", "Asia/Singapore", 9, 0, 17, 0),
    "KOSPI": ("^KS11", "South Korea", "Asia/Seoul", 9, 0, 15, 30),
    "FTSE 100": ("^FTSE", "UK", "Europe/London", 8, 0, 16, 30),
}

cache: dict[str, dict[str, Any]] = {}
cache_lock = Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_state(timezone_name: str, open_hour: int, open_minute: int, close_hour: int, close_minute: int) -> tuple[str, str]:
    local_now = datetime.now(ZoneInfo(timezone_name))
    current = local_now.hour * 60 + local_now.minute
    opens = open_hour * 60 + open_minute
    closes = close_hour * 60 + close_minute
    if local_now.weekday() >= 5:
        return "offline", "Weekend"
    if opens <= current < closes:
        return "active", "Regular session"
    return "offline", "Outside regular session"


def quote_from_yahoo(symbol: str) -> dict[str, Any]:
    response = httpx.get(
        YAHOO_CHART_URL.format(symbol=symbol),
        params={"range": "1d", "interval": "1m"},
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    response.raise_for_status()
    result = response.json()["chart"]["result"][0]
    meta = result["meta"]
    value = meta.get("regularMarketPrice") or meta.get("previousClose")
    previous = meta.get("previousClose") or meta.get("chartPreviousClose")
    if value is None or previous in (None, 0):
        raise ValueError(f"Yahoo returned no usable quote for {symbol}")
    timestamp = datetime.fromtimestamp(
        meta.get("regularMarketTime", result["timestamp"][-1]), timezone.utc
    ).isoformat()
    change = value - previous
    return {
        "value": value,
        "change": change,
        "change_percent": change / previous * 100,
        "timestamp": timestamp,
        "source": f"Yahoo Finance ({symbol})",
    }


def quote_from_nse(index_name: str) -> dict[str, Any]:
    response = httpx.get(
        NSE_INDICES_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=10,
    )
    response.raise_for_status()
    indices = response.json()["data"]
    match = next((item for item in indices if item.get("index") == index_name), None)
    if not match:
        raise ValueError(f"NSE returned no {index_name} quote")
    value = match["last"]
    change = match["change"]
    return {
        "value": value,
        "change": change,
        "change_percent": match["percentChange"],
        "timestamp": now_iso(),
        "source": "NSE India",
    }


def breadth_from_nse() -> dict[str, Any]:
    response = httpx.get(
        NSE_INDICES_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=10,
    )
    response.raise_for_status()
    nifty = next(
        item for item in response.json()["data"] if item.get("index") == "NIFTY 50"
    )
    advances = int(nifty["advances"])
    declines = int(nifty["declines"])
    unchanged = int(nifty["unchanged"])
    return {
        "advances": advances,
        "declines": declines,
        "unchanged": unchanged,
        "ratio": round(advances / declines, 2) if declines else 0,
        "timestamp": now_iso(),
        "source": "NSE India",
    }


def snapshot(label: str, name: str, quote: dict[str, Any] | None, error: str | None = None) -> dict[str, Any]:
    with cache_lock:
        if quote:
            cache[label] = quote
        cached = cache.get(label)

    if cached:
        result = {**cached, "status": "positive" if cached["change"] >= 0 else "negative"}
        if error:
            result["freshness"] = "stale"
            result["error"] = error
        else:
            result["freshness"] = "live"
        return {"symbol": label, "name": name, **result}

    return {
        "symbol": label,
        "name": name,
        "value": 0,
        "change": 0,
        "change_percent": 0,
        "status": "neutral",
        "timestamp": None,
        "source": "Unavailable",
        "freshness": "unavailable",
        "error": error or "No quote available",
    }


def collect_snapshot(label: str, name: str) -> dict[str, Any]:
    try:
        result = snapshot(label, name, quote_from_yahoo(YAHOO_SYMBOLS[label]))
    except Exception as exc:
        result = snapshot(label, name, None, str(exc))
    session = MARKET_SESSIONS.get(label)
    if session:
        result["market_state"], result["market_state_reason"] = session_state(*session)
    return result


def collect_gift_nifty() -> dict[str, Any]:
    symbol = os.getenv("GIFT_NIFTY_YAHOO_SYMBOL")
    if not symbol:
        return snapshot(
            "GIFT NIFTY",
            "GIFT NIFTY",
            None,
            "No GIFT_NIFTY_YAHOO_SYMBOL configured",
        )
    try:
        return snapshot("GIFT NIFTY", "GIFT NIFTY", quote_from_yahoo(symbol))
    except Exception as exc:
        return snapshot("GIFT NIFTY", "GIFT NIFTY", None, str(exc))


def collect_global_exchanges() -> list[dict[str, Any]]:
    def collect(item: tuple[str, tuple[str, str, str, int, int, int, int]]) -> dict[str, Any]:
        label, (symbol, country, timezone_name, open_hour, open_minute, close_hour, close_minute) = item
        try:
            result = snapshot(label, label, quote_from_yahoo(symbol))
        except Exception as exc:
            result = snapshot(label, label, None, str(exc))
        result["country"] = country
        result["market_state"], result["market_state_reason"] = session_state(timezone_name, open_hour, open_minute, close_hour, close_minute)
        return result

    with ThreadPoolExecutor(max_workers=len(GLOBAL_SYMBOLS)) as executor:
        return list(executor.map(collect, GLOBAL_SYMBOLS.items()))


def collect_institutional_flow() -> dict[str, Any]:
    try:
        response = httpx.get(
            NSE_FII_DII_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        rows = response.json()
        rows = rows if isinstance(rows, list) else rows.get("data", [])
        latest_date = rows[0]["date"]
        latest_rows = [row for row in rows if row.get("date") == latest_date]
        fii = next((row for row in latest_rows if row.get("category") == "FII/FPI"), None)
        dii = next((row for row in latest_rows if row.get("category") == "DII"), None)
        if not fii or not dii:
            raise ValueError("NSE returned no FII/FPI and DII rows")
        return {
            "fii_net": float(str(fii["netValue"]).replace(",", "")),
            "dii_net": float(str(dii["netValue"]).replace(",", "")),
            "timestamp": latest_date or now_iso(),
            "source": "NSE India FII/DII",
            "freshness": "live",
        }
    except Exception as exc:
        return {"fii_net": None, "dii_net": None, "timestamp": None, "source": "Unavailable", "freshness": "unavailable", "error": str(exc)}


def collect_macro() -> dict[str, Any]:
    macro_symbols = {
        "DOLLAR INDEX": "DX-Y.NYB",
        "US 10Y YIELD": "^TNX",
    }
    def collect_macro_quote(item: tuple[str, str]) -> dict[str, Any]:
        label, symbol = item
        try:
            return snapshot(label, label, quote_from_yahoo(symbol))
        except Exception as exc:
            return snapshot(label, label, None, str(exc))

    with ThreadPoolExecutor(max_workers=2) as executor:
        quotes = list(executor.map(collect_macro_quote, macro_symbols.items()))
    configured_rate = os.getenv("FED_FUNDS_RATE")
    configured_date = os.getenv("FED_NEXT_REVISION_DATE")
    fed = {
        "value": float(configured_rate) if configured_rate else None,
        "next_revision_date": configured_date,
        "timestamp": now_iso() if configured_rate else None,
        "source": "Configured environment value" if configured_rate else "Unavailable",
        "freshness": "live" if configured_rate else "unavailable",
    }
    return {
        "dollar_index": quotes[0],
        "fed_funds_rate": fed,
        "us_treasury_10y": quotes[1],
        "institutional_flow": collect_institutional_flow(),
    }


def collect_overview() -> dict[str, Any]:
    labels = [(label, DISPLAY_NAMES[label]) for label in YAHOO_SYMBOLS]
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda item: collect_snapshot(*item), labels))
    by_symbol = {item["symbol"]: item for item in results}

    try:
        breadth = breadth_from_nse()
        breadth_status = "positive" if breadth["advances"] >= breadth["declines"] else "negative"
        breadth.update({"status": breadth_status, "freshness": "live"})
    except Exception as exc:
        breadth = {"advances": 0, "declines": 0, "unchanged": 0, "ratio": 0, "status": "neutral", "timestamp": None, "source": "Unavailable", "freshness": "unavailable", "error": str(exc)}

    positive = sum(item["status"] == "positive" for item in results + [breadth])
    score = round(positive / 6 * 100)
    gift_nifty = collect_gift_nifty()
    global_exchanges = collect_global_exchanges()
    macro = collect_macro()
    factors = [
        {
            "label": item["name"],
            "value": f"{item['change_percent']:+.2f}%",
            "signal": item["status"],
            "detail": item["source"],
        }
        for item in results[:2]
    ]
    factors.extend(
        [
            {
                "label": "India VIX",
                "value": f"{by_symbol['INDIA VIX']['value']:.2f}",
                "signal": by_symbol["INDIA VIX"]["status"],
                "detail": by_symbol["INDIA VIX"]["source"],
            },
            {
                "label": "Market Breadth",
                "value": f"{breadth['ratio']:.2f}x",
                "signal": breadth["status"],
                "detail": breadth["source"],
            },
            {
                "label": "GIFT NIFTY",
                "value": "Unavailable" if gift_nifty["freshness"] == "unavailable" else "Connected",
                "signal": gift_nifty["status"],
                "detail": gift_nifty["source"],
            },
        ]
    )
    return {
        "as_of": now_iso(),
        "overall_signal": "BULLISH" if score >= 60 else "BEARISH" if score <= 40 else "NEUTRAL",
        "score": score,
        "confidence": "High" if score in (0, 17, 83, 100) else "Moderate",
        "global_markets": [by_symbol["NASDAQ"], by_symbol["DOW"]],
        "global_exchanges": global_exchanges,
        "macro": macro,
        "india_vix": by_symbol["INDIA VIX"],
        "breadth": breadth,
        "gift_nifty": gift_nifty,
        "nifty50": by_symbol["NIFTY 50"],
        "bank_nifty": by_symbol["BANK NIFTY"],
        "factors": factors,
    }
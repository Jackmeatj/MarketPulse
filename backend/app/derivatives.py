from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

import httpx

NSE_OPTION_CHAIN_URL = os.getenv(
    "OPTIONS_CHAIN_URL",
    "https://www.nseindia.com/api/option-chain-indices",
)
USER_AGENT = "Mozilla/5.0 (MarketPulse/0.4)"


def empty_derivatives(symbol: str, error: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "timestamp": None,
        "source": "Unavailable",
        "freshness": "unavailable",
        "underlying_value": None,
        "pcr": None,
        "max_pain": None,
        "support": None,
        "resistance": None,
        "signal": "UNAVAILABLE",
        "error": error,
        "expiries": [],
        "strikes": [],
    }


def collect_option_chain(symbol: str | None = None) -> dict[str, Any]:
    symbol = symbol or os.getenv("NSE_OPTION_SYMBOL", "NIFTY")
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15, follow_redirects=True) as client:
            client.get("https://www.nseindia.com", timeout=10)
            response = client.get(NSE_OPTION_CHAIN_URL, params={"symbol": symbol})
            response.raise_for_status()
        payload = response.json()
        records = payload["records"]
        expiry = records["expiryDates"][0]
        rows = [row for row in records["data"] if row.get("expiryDate") == expiry]
        calls = {row["strikePrice"]: row.get("CE", {}) for row in rows}
        puts = {row["strikePrice"]: row.get("PE", {}) for row in rows}
        strikes = sorted(set(calls) | set(puts))
        call_oi = sum(float(calls[strike].get("openInterest", 0)) for strike in strikes)
        put_oi = sum(float(puts[strike].get("openInterest", 0)) for strike in strikes)
        call_change = sum(float(calls[strike].get("changeinOpenInterest", 0)) for strike in strikes)
        put_change = sum(float(puts[strike].get("changeinOpenInterest", 0)) for strike in strikes)
        max_pain = min(
            strikes,
            key=lambda target: sum(
                max(target - strike, 0) * calls[strike].get("openInterest", 0)
                + max(strike - target, 0) * puts[strike].get("openInterest", 0)
                for strike in strikes
            ),
        )
        support = max(strikes, key=lambda strike: puts[strike].get("openInterest", 0))
        resistance = max(strikes, key=lambda strike: calls[strike].get("openInterest", 0))
        underlying = records.get("underlyingValue")
        atm_strike = min(strikes, key=lambda strike: abs(strike - underlying)) if underlying else strikes[len(strikes) // 2]
        atm_iv = {
            "call": calls[atm_strike].get("impliedVolatility"),
            "put": puts[atm_strike].get("impliedVolatility"),
        }
        pcr = put_oi / call_oi if call_oi else None
        signal = "BULLISH" if pcr and pcr > 1.05 else "BEARISH" if pcr and pcr < 0.85 else "NEUTRAL"
        return {
            "symbol": symbol,
            "timestamp": records.get("timestamp"),
            "source": "NSE India Option Chain",
            "freshness": "live",
            "underlying_value": records.get("underlyingValue"),
            "atm_strike": atm_strike,
            "atm_iv": atm_iv,
            "pcr": pcr,
            "max_pain": max_pain,
            "support": support,
            "resistance": resistance,
            "signal": signal,
            "error": None,
            "expiry": expiry,
            "expiries": records.get("expiryDates", [])[:4],
            "strikes": [
                {"strike": strike, "call_oi": calls[strike].get("openInterest", 0), "put_oi": puts[strike].get("openInterest", 0), "call_change_oi": calls[strike].get("changeinOpenInterest", 0), "put_change_oi": puts[strike].get("changeinOpenInterest", 0), "call_iv": calls[strike].get("impliedVolatility"), "put_iv": puts[strike].get("impliedVolatility")}
                for strike in strikes
            ],
            "totals": {"call_oi": call_oi, "put_oi": put_oi, "call_change_oi": call_change, "put_change_oi": put_change},
        }
    except Exception as exc:
        return empty_derivatives(symbol, str(exc))


def build_recommendation(overview: dict[str, Any], derivatives: dict[str, Any]) -> dict[str, Any]:
    signals = [overview["overall_signal"]]
    if derivatives["signal"] != "UNAVAILABLE":
        signals.append(derivatives["signal"])
    bullish = signals.count("BULLISH")
    bearish = signals.count("BEARISH")
    bias = "BULLISH" if bullish > bearish else "BEARISH" if bearish > bullish else "NEUTRAL"
    setups = []
    if bias == "BULLISH" and derivatives.get("support"):
        setups.append({"instrument": derivatives["symbol"], "direction": "CALL / LONG", "trigger": f"Above {derivatives['support']}", "risk": f"Below {derivatives['support']}", "reason": "Market score and options positioning align bullishly."})
    elif bias == "BEARISH" and derivatives.get("resistance"):
        setups.append({"instrument": derivatives["symbol"], "direction": "PUT / SHORT", "trigger": f"Below {derivatives['resistance']}", "risk": f"Above {derivatives['resistance']}", "reason": "Market score and options positioning align bearishly."})
    return {"bias": bias, "market_score": overview["score"], "derivatives_signal": derivatives["signal"], "setups": setups, "disclaimer": "Research output only. Validate liquidity, execution, and risk before trading."}
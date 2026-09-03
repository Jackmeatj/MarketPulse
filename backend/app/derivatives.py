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


def build_recommendation(
    overview: dict[str, Any],
    sectors: dict[str, Any],
    derivatives: dict[str, Any],
) -> dict[str, Any]:
    sector_items = [item for item in sectors.get("items", []) if item.get("score") is not None]
    leading_sector = max(sector_items, key=lambda item: item["score"]) if sector_items else None
    market_score = float(overview.get("score") or 50)
    sector_score = float(leading_sector["score"]) if leading_sector else None
    derivatives_score = None
    if derivatives.get("signal") == "BULLISH":
        derivatives_score = 75
    elif derivatives.get("signal") == "BEARISH":
        derivatives_score = 25
    elif derivatives.get("signal") == "NEUTRAL":
        derivatives_score = 50

    available_scores = [score for score in (market_score, sector_score, derivatives_score) if score is not None]
    overall_score = round(sum(available_scores) / len(available_scores)) if available_scores else None
    bullish = sum(score >= 60 for score in available_scores)
    bearish = sum(score <= 40 for score in available_scores)
    bias = "BULLISH" if bullish > bearish else "BEARISH" if bearish > bullish else "NEUTRAL"
    classification = (
        "HIGH_CONVICTION_WATCH" if overall_score is not None and overall_score >= 75
        else "CONSTRUCTIVE" if overall_score is not None and overall_score >= 60
        else "MONITOR" if overall_score is not None and overall_score >= 45
        else "INSUFFICIENT_EVIDENCE"
    )
    trading_score = round(sum(score for score in (market_score, derivatives_score) if score is not None) / len([score for score in (market_score, derivatives_score) if score is not None]))
    investment_score = round(sum(score for score in (sector_score, market_score) if score is not None) / len([score for score in (sector_score, market_score) if score is not None]))
    setups = []
    if bias == "BULLISH" and derivatives.get("resistance"):
        setups.append({"instrument": derivatives["symbol"], "direction": "CALL / LONG", "trigger": f"Above {derivatives['resistance']}", "risk": f"Below {derivatives.get('support', 'support')}", "reason": "Market direction and options positioning align bullishly."})
    elif bias == "BEARISH" and derivatives.get("support"):
        setups.append({"instrument": derivatives["symbol"], "direction": "PUT / SHORT", "trigger": f"Below {derivatives['support']}", "risk": f"Above {derivatives.get('resistance', 'resistance')}", "reason": "Market direction and options positioning align bearishly."})
    return {
        "symbol": derivatives.get("symbol", "NIFTY"),
        "bias": bias,
        "classification": classification,
        "overall_score": overall_score,
        "investment_score": investment_score,
        "trading_score": trading_score,
        "market_score": round(market_score),
        "derivatives_signal": derivatives.get("signal", "UNAVAILABLE"),
        "leading_sector": leading_sector.get("sector") if leading_sector else None,
        "scores": {
            "fundamentals": None,
            "growth": None,
            "sector": round(sector_score) if sector_score is not None else None,
            "technical": round(market_score),
            "relative_strength": round(sector_score) if sector_score is not None else None,
            "volume": None,
            "catalyst": None,
            "valuation": None,
            "risk": None,
            "derivatives": round(derivatives_score) if derivatives_score is not None else None,
        },
        "thesis": [
            f"Market environment is {overview.get('overall_signal', 'UNAVAILABLE')}.",
            f"{leading_sector['sector']} leads the available sector universe." if leading_sector else "Sector leadership is unavailable.",
            f"Options positioning is {derivatives.get('signal', 'UNAVAILABLE').lower()}.",
        ],
        "catalysts": [],
        "risks": [
            "Fundamental, valuation and corporate-disclosure feeds are not connected yet.",
            "This is a market setup, not a company-specific investment thesis.",
        ],
        "setups": setups,
        "data_quality": {
            "status": "PROVISIONAL",
            "available_engines": len(available_scores),
            "pending_engines": 6,
            "missing_inputs": ["fundamentals", "growth", "volume", "catalysts", "valuation", "risk"],
        },
        "disclaimer": "Research output only. Not investment advice. Validate sources, liquidity, execution, and risk before trading.",
    }
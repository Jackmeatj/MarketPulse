from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

NSE_INDICES_URL = "https://www.nseindia.com/api/allIndices"
USER_AGENT = "Mozilla/5.0 (MarketPulse/0.5)"

CORE_SECTORS = {
    "Auto": "NIFTY AUTO",
    "Bank": "NIFTY BANK",
    "Financial Services": "NIFTY FINANCIAL SERVICES",
    "IT": "NIFTY IT",
    "Pharma": "NIFTY PHARMA",
    "Healthcare": "NIFTY HEALTHCARE INDEX",
    "FMCG": "NIFTY FMCG",
    "Metal": "NIFTY METAL",
    "Realty": "NIFTY REALTY",
    "PSU Bank": "NIFTY PSU BANK",
    "Private Bank": "NIFTY PRIVATE BANK",
    "Oil & Gas": "NIFTY OIL & GAS",
    "Power": "NIFTY ENERGY",
    "Consumer Durables": "NIFTY CONSUMER DURABLES",
    "Capital Goods": "NIFTY CAPITAL MARKETS",
    "Cement": "NIFTY CEMENT",
    "Chemicals": "NIFTY CHEMICALS",
    "Media": "NIFTY MEDIA",
    "Telecommunications": "NIFTY INDIA DIGITAL",
    "Construction": "NIFTY INFRASTRUCTURE",
}


def unavailable_sector(name: str, index_name: str, error: str) -> dict[str, Any]:
    return {
        "sector": name,
        "index_name": index_name,
        "value": None,
        "change_percent": None,
        "relative_strength": None,
        "score": None,
        "classification": "UNAVAILABLE",
        "trend_score": None,
        "momentum_score": None,
        "breadth_score": None,
        "velocity_score": None,
        "volatility_score": None,
        "advances": None,
        "declines": None,
        "unchanged": None,
        "timestamp": None,
        "source": "Unavailable",
        "freshness": "unavailable",
        "error": error,
    }


def collect_sectors() -> dict[str, Any]:
    try:
        response = httpx.get(
            NSE_INDICES_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        rows = {row.get("index"): row for row in response.json()["data"]}
        benchmark = rows.get("NIFTY 50")
        if not benchmark:
            raise ValueError("NSE returned no NIFTY 50 benchmark")
        benchmark_return = float(benchmark.get("percentChange") or 0)
        items = []
        for name, index_name in CORE_SECTORS.items():
            row = rows.get(index_name)
            if not row:
                items.append(unavailable_sector(name, index_name, "NSE index is not present in the current response"))
                continue
            change_percent = float(row.get("percentChange") or 0)
            relative_strength = change_percent - benchmark_return
            advances = row.get("advances")
            declines = row.get("declines")
            unchanged = row.get("unchanged")
            breadth_score = None
            if advances is not None and declines is not None:
                total = int(advances) + int(declines) + int(unchanged or 0)
                breadth_score = round(int(advances) / total * 100) if total else None
            trend_score = max(0, min(100, round(50 + change_percent * 12)))
            momentum_score = max(0, min(100, round(50 + relative_strength * 15)))
            score = round(trend_score * 0.35 + momentum_score * 0.35 + (breadth_score or 50) * 0.2 + 50 * 0.1)
            classification = "LEADER" if score >= 60 else "POSITIVE" if score >= 55 else "WEAK" if score < 40 else "NEUTRAL"
            items.append({
                "sector": name,
                "index_name": index_name,
                "value": row.get("last"),
                "change_percent": change_percent,
                "relative_strength": round(relative_strength, 2),
                "score": score,
                "classification": classification,
                "trend_score": trend_score,
                "momentum_score": momentum_score,
                "breadth_score": breadth_score,
                "velocity_score": None,
                "volatility_score": None,
                "advances": advances,
                "declines": declines,
                "unchanged": unchanged,
                "timestamp": row.get("timeVal") or datetime.now(timezone.utc).isoformat(),
                "source": "NSE India sectoral indices",
                "freshness": "live",
                "error": None,
            })
        items.sort(key=lambda item: item["score"] if item["score"] is not None else -1, reverse=True)
        leaders = [item["sector"] for item in items if item["classification"] == "LEADER"][:4]
        weak = [item["sector"] for item in items if item["classification"] in ("WEAK", "UNAVAILABLE")][:4]
        improving = [item["sector"] for item in items if item["relative_strength"] is not None and item["relative_strength"] > 0][:4]
        return {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "benchmark": {"name": "NIFTY 50", "change_percent": benchmark_return},
            "source": "NSE India sectoral indices",
            "freshness": "live" if any(item["freshness"] == "live" for item in items) else "unavailable",
            "items": items,
            "rotation": {"leaders": leaders, "improving": improving, "weak": weak},
            "limitations": [
                "Trend and momentum are 1D proxies until historical candles are ingested.",
                "Constituent breadth, velocity, ATR and long-horizon relative strength require constituent and historical feeds.",
            ],
        }
    except Exception as exc:
        return {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "benchmark": {"name": "NIFTY 50", "change_percent": None},
            "source": "Unavailable",
            "freshness": "unavailable",
            "items": [unavailable_sector(name, index_name, str(exc)) for name, index_name in CORE_SECTORS.items()],
            "rotation": {"leaders": [], "improving": [], "weak": list(CORE_SECTORS)[:4]},
            "limitations": [str(exc)],
        }
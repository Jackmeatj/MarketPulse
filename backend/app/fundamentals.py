from __future__ import annotations

from typing import Any

from .nse_metrics import calculate_symbol_metrics


def collect_fundamentals(symbol: str) -> dict[str, Any]:
    empty_metrics = {
        "revenue_cagr_3y": None, "profit_cagr_3y": None, "eps_cagr_3y": None,
        "pe": None, "pb": None, "ev_ebitda": None, "debt_to_equity": None,
        "cfo_to_pat": None, "atr_14": None, "atr_percent": None,
    }
    try:
        result = calculate_symbol_metrics(symbol)
    except Exception as exc:
        return {"status": "pending", "source": "NSE/BSE filings + normalized MarketPulse engine", "symbol": symbol.upper(), "scores": {"fundamentals": None, "growth": None, "valuation": None}, "metrics": empty_metrics, "limitations": [f"Analytics unavailable: {exc}"]}

    metrics = {**empty_metrics, **result["growth"], **result["valuation"], **result["risk"], **result["technical"]}
    available = [value for value in metrics.values() if value is not None]
    growth_values = [metrics[key] for key in ("revenue_cagr_3y", "profit_cagr_3y", "eps_cagr_3y") if metrics[key] is not None]
    valuation_values = [metrics[key] for key in ("pe", "pb", "ev_ebitda") if metrics[key] is not None]
    scores = {
        "fundamentals": round(min(100, len(available) / len(metrics) * 100)) if available else None,
        "growth": round(min(100, 50 + sum(growth_values) / len(growth_values))) if growth_values else None,
        "valuation": round(min(100, max(0, 100 - sum(valuation_values) / len(valuation_values) * 2))) if valuation_values else None,
    }
    return {"status": "live" if available else "pending", "source": "NSE/BSE filings + normalized MarketPulse engine", "symbol": symbol.upper(), "scores": scores, "metrics": metrics, "catalyst_score": result.get("catalyst"), "catalyst_reasons": result.get("catalyst_reasons", []), "limitations": [] if available else ["No normalized NSE/BSE financial or historical rows are stored for this symbol yet."]}

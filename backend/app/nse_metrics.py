from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import mean, pstdev
from typing import Any

from .storage import postgres_connection


def _safe_float(value: Any) -> float | None:
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


def _latest_statement_rows(symbol: str, statement_type: str, metric_name: str | None = None) -> list[dict[str, Any]]:
    with postgres_connection() as connection:
        query = """
            SELECT symbol, statement_type, period_end, period_kind, metric_name, metric_value, currency, source
            FROM financial_statements
            WHERE symbol = %s AND statement_type = %s
        """
        params: list[Any] = [symbol, statement_type]
        if metric_name:
            query += " AND metric_name = %s"
            params.append(metric_name)
        query += " ORDER BY period_end DESC, created_at DESC"
        return connection.execute(query, params).fetchall()


def _latest_price_rows(symbol: str, lookback_days: int = 365) -> list[dict[str, Any]]:
    with postgres_connection() as connection:
        cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
        rows = connection.execute(
            """
            SELECT symbol, trade_date, open_price, high_price, low_price, close_price, volume
            FROM nse_daily_prices
            WHERE symbol = %s AND trade_date >= %s
            ORDER BY trade_date ASC
            """,
            (symbol, cutoff),
        ).fetchall()
        return rows


def _cagr(values: list[float], periods: int) -> float | None:
    if len(values) < periods + 1:
        return None
    start = values[0]
    end = values[-1]
    if start in (None, 0) or end in (None, 0):
        return None
    return ((end / start) ** (1 / periods) - 1) * 100


def _growth_scores(symbol: str) -> dict[str, float | None]:
    rows = _latest_statement_rows(symbol, "profit_loss")
    by_metric: dict[str, list[float]] = {}
    for row in rows:
        value = _safe_float(row["metric_value"])
        if value is None:
            continue
        by_metric.setdefault(row["metric_name"], []).append(value)

    revenue = list(reversed(by_metric.get("revenue", [])))
    profit = list(reversed(by_metric.get("pat", [])))
    eps = list(reversed(by_metric.get("eps", [])))

    return {
        "revenue_cagr_3y": _cagr(revenue[:4], 3) if len(revenue) >= 4 else None,
        "profit_cagr_3y": _cagr(profit[:4], 3) if len(profit) >= 4 else None,
        "eps_cagr_3y": _cagr(eps[:4], 3) if len(eps) >= 4 else None,
    }


def _valuation_scores(symbol: str) -> dict[str, float | None]:
    rows = _latest_statement_rows(symbol, "balance_sheet")
    metrics: dict[str, list[float]] = {}
    for row in rows:
        value = _safe_float(row["metric_value"])
        if value is None:
            continue
        metrics.setdefault(row["metric_name"], []).append(value)

    price_rows = _latest_price_rows(symbol)
    close = price_rows[-1]["close_price"] if price_rows else None
    if close is None:
        try:
            from .stocks import yahoo_history

            close = yahoo_history(symbol)["close"]
        except Exception:
            close = None
    if close is None:
        return {"pe": None, "pb": None, "ev_ebitda": None}
    paid_up_capital = _safe_float(metrics.get("paid_up_capital", [0])[-1]) or 0.0
    face_value = _safe_float(metrics.get("face_value", [0])[-1]) or 0.0
    latest_market_cap = close * paid_up_capital / face_value if face_value else None
    debt = sum(v for v in [
        _safe_float(metrics.get("borrowings", [0])[-1]),
        _safe_float(metrics.get("total_debt", [0])[-1]),
    ] if v is not None)
    cash = _safe_float(metrics.get("cash_and_equivalents", [0])[-1]) or 0.0
    ebitda = _safe_float(_latest_statement_rows(symbol, "profit_loss", "ebitda")[0]["metric_value"]) if _latest_statement_rows(symbol, "profit_loss", "ebitda") else None
    eps = _safe_float(_latest_statement_rows(symbol, "profit_loss", "eps")[0]["metric_value"]) if _latest_statement_rows(symbol, "profit_loss", "eps") else None

    pe = (close / eps) if close and eps else None
    pb = None
    ev_ebitda = None
    if ebitda and ebitda != 0:
        if latest_market_cap is not None:
            ev_value = latest_market_cap + debt - cash
            ev_ebitda = ev_value / ebitda
    return {"pe": pe, "pb": pb, "ev_ebitda": ev_ebitda}


def _risk_scores(symbol: str) -> dict[str, float | None]:
    rows = _latest_statement_rows(symbol, "balance_sheet")
    metrics: dict[str, float | None] = {}
    for row in rows:
        value = _safe_float(row["metric_value"])
        if value is not None:
            metrics[row["metric_name"]] = value

    debt = metrics.get("borrowings") or metrics.get("total_debt") or 0.0
    equity = metrics.get("equity") or metrics.get("net_worth") or 0.0
    if equity and equity > 0:
        debt_equity = debt / equity
    else:
        debt_equity = None

    cash_rows = _latest_statement_rows(symbol, "cash_flow", "operating_cash_flow")
    operating_cf = _safe_float(cash_rows[0]["metric_value"]) if cash_rows else None
    pat_rows = _latest_statement_rows(symbol, "profit_loss", "pat")
    pat = _safe_float(pat_rows[0]["metric_value"]) if pat_rows else None
    cfo_to_pat = (operating_cf / pat) if operating_cf is not None and pat and pat != 0 else None

    return {"debt_to_equity": debt_equity, "cfo_to_pat": cfo_to_pat}


def _catalyst_score(symbol: str) -> tuple[float | None, list[str]]:
    with postgres_connection() as connection:
        rows = connection.execute(
            "SELECT event_type, title FROM corporate_events WHERE symbol = %s ORDER BY event_date DESC LIMIT 20",
            (symbol,),
        ).fetchall()
    if not rows:
        return None, []
    positive = ("ORDER", "ACQUISITION", "CAPACITY", "DIVIDEND", "APPROVAL", "FUND")
    negative = ("PLEDGE", "DOWNGRADE", "RESIGN", "LITIGATION", "PENALTY", "DEFAULT")
    score = 50
    reasons: list[str] = []
    for row in rows:
        text = f"{row['event_type']} {row['title'] or ''}".upper()
        label = row["title"] or row["event_type"]
        if any(token in text for token in positive):
            score += 5
            reasons.append(label)
        elif any(token in text for token in negative):
            score -= 5
            reasons.append(label)
        else:
            reasons.append(label)
    return max(0, min(100, score)), reasons[:5]


def _atr_score(symbol: str) -> dict[str, float | None]:
    rows = _latest_price_rows(symbol, lookback_days=300)
    if len(rows) < 15:
        return {"atr_14": None, "atr_percent": None}

    closes = [float(item["close_price"]) for item in rows if item["close_price"] is not None]
    highs = [float(item["high_price"]) for item in rows if item["high_price"] is not None]
    lows = [float(item["low_price"]) for item in rows if item["low_price"] is not None]

    tr_values: list[float] = []
    for i in range(1, len(rows)):
        previous_close = rows[i - 1]["close_price"]
        if previous_close is None:
            continue
        tr_values.append(max(
            highs[i] - lows[i],
            abs(highs[i] - previous_close),
            abs(lows[i] - previous_close),
        ))

    if not tr_values:
        return {"atr_14": None, "atr_percent": None}
    atr_14 = mean(tr_values[-14:])
    recent_close = closes[-1]
    atr_percent = (atr_14 / recent_close) * 100 if recent_close else None
    return {"atr_14": atr_14, "atr_percent": atr_percent}


def calculate_symbol_metrics(symbol: str) -> dict[str, Any]:
    symbol = symbol.upper()
    growth = _growth_scores(symbol)
    valuation = _valuation_scores(symbol)
    risk = _risk_scores(symbol)
    atr = _atr_score(symbol)
    catalyst, catalyst_reasons = _catalyst_score(symbol)
    return {
        "symbol": symbol,
        "growth": growth,
        "valuation": valuation,
        "risk": risk,
        "catalyst": catalyst,
        "catalyst_reasons": catalyst_reasons,
        "technical": {"atr_14": atr.get("atr_14"), "atr_percent": atr.get("atr_percent")},
        "computed_at": datetime.utcnow().isoformat(),
    }


def recalculate_engine_metrics() -> dict[str, Any]:
    with postgres_connection() as connection:
        symbols = [row[0] for row in connection.execute("SELECT DISTINCT symbol FROM nse_daily_prices ORDER BY symbol").fetchall()]
    results = {symbol: calculate_symbol_metrics(symbol) for symbol in symbols}
    return {"status": "ok", "symbols": len(symbols), "results": results}

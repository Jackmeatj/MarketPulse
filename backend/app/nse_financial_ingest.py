from __future__ import annotations

import csv
import io
import json
import os
from datetime import date, datetime
from typing import Any
import xml.etree.ElementTree as ET

import httpx

from .storage import postgres_connection

NSE_BASE_URL = "https://www.nseindia.com"
FINANCIAL_RESULTS_URL = os.getenv("NSE_FINANCIAL_RESULTS_URL", f"{NSE_BASE_URL}/api/corporates-financial-results")
ANNOUNCEMENTS_URL = os.getenv("NSE_ANNOUNCEMENTS_URL", f"{NSE_BASE_URL}/api/corporate-announcements")
NSE_HEADERS = {"User-Agent": "Mozilla/5.0 (MarketPulse/0.6)", "Accept": "application/json,text/csv,*/*"}


def _nse_get(url: str, params: dict[str, str]) -> httpx.Response:
    with httpx.Client(headers=NSE_HEADERS, timeout=20, follow_redirects=True) as client:
        client.get(NSE_BASE_URL)
        response = client.get(url, params=params)
        response.raise_for_status()
        return response


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


def _normalize_metric_name(name: str) -> str:
    return (name or "").strip().lower().replace(" ", "_").replace("-", "_")


def _fetch_nse_financial_result_csv(symbol: str) -> list[dict[str, Any]]:
    response = _nse_get(FINANCIAL_RESULTS_URL, {"symbol": symbol, "index": "equities", "period": "Quarterly"})
    if "csv" in response.headers.get("content-type", "") or response.text.lstrip().startswith(("symbol,", "SYMBOL,")):
        return list(csv.DictReader(io.StringIO(response.text)))
    payload = response.json()
    rows = payload.get("data", payload) if isinstance(payload, dict) else payload
    return rows if isinstance(rows, list) else []


def _parse_xbrl_facts(symbol: str, filing: dict[str, Any]) -> list[dict[str, Any]]:
    xbrl_url = filing.get("xbrl")
    if not xbrl_url or xbrl_url.endswith("/-"):
        return []
    response = _nse_get(xbrl_url, {})
    root = ET.fromstring(response.content)
    contexts: dict[str, tuple[date, date, bool]] = {}
    for context in root.iter():
        if context.tag.rsplit("}", 1)[-1] != "context":
            continue
        context_id = context.attrib.get("id")
        dates = [child.text for child in context.iter() if child.tag.rsplit("}", 1)[-1] in {"startDate", "endDate"}]
        if not context_id or len(dates) != 2 or not all(dates):
            continue
        try:
            start = date.fromisoformat(dates[0])
            end = date.fromisoformat(dates[1])
        except ValueError:
            continue
        has_dimensions = any(child.tag.rsplit("}", 1)[-1] == "scenario" for child in context)
        contexts[context_id] = (start, end, has_dimensions)

    concept_map = {
        "Income": ("profit_loss", "revenue"),
        "InterestEarned": ("profit_loss", "revenue"),
        "ProfitLossForThePeriod": ("profit_loss", "pat"),
        "ProfitLossFromOrdinaryActivitiesAfterTax": ("profit_loss", "pat"),
        "BasicEarningsPerShareAfterExtraordinaryItems": ("profit_loss", "eps"),
        "DilutedEarningsPerShareAfterExtraordinaryItems": ("profit_loss", "eps"),
        "OperatingProfitBeforeProvisionAndContingencies": ("profit_loss", "ebitda"),
        "TotalAssets": ("balance_sheet", "total_assets"),
        "Equity": ("balance_sheet", "equity"),
        "NetWorth": ("balance_sheet", "net_worth"),
        "Borrowings": ("balance_sheet", "borrowings"),
        "TotalDebt": ("balance_sheet", "total_debt"),
        "CashAndCashEquivalents": ("balance_sheet", "cash_and_equivalents"),
        "PaidUpValueOfEquityShareCapital": ("balance_sheet", "paid_up_capital"),
        "FaceValueOfEquityShareCapital": ("balance_sheet", "face_value"),
    }
    rows: list[dict[str, Any]] = []
    for fact in root:
        concept = fact.tag.rsplit("}", 1)[-1]
        mapping = concept_map.get(concept)
        context = contexts.get(fact.attrib.get("contextRef", ""))
        if not mapping or context is None or fact.text is None or context[2]:
            continue
        value = _safe_float(fact.text)
        if value is None:
            continue
        statement_type, metric_name = mapping
        rows.append({
            "statement_type": statement_type,
            "period_end": context[1].isoformat(),
            "period_kind": "annual" if (context[1] - context[0]).days >= 300 else "quarterly",
            "metric_name": metric_name,
            "metric_value": value if metric_name in {"eps", "face_value"} else value / 10000000,
            "currency": "INR",
            "source": "NSE XBRL",
            "source_ref": xbrl_url,
        })
    return rows


def fetch_nse_corporate_events(symbol: str) -> list[dict[str, Any]]:
    response = _nse_get(ANNOUNCEMENTS_URL, {"symbol": symbol, "index": "equities"})
    payload = response.json()
    rows = payload.get("data", payload) if isinstance(payload, dict) else payload
    return rows if isinstance(rows, list) else []


def store_financial_statement_rows(symbol: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    with postgres_connection() as connection:
        inserted = 0
        for row in rows:
            statement_type = (row.get("statement_type") or "profit_loss").lower()
            period_end = row.get("period_end")
            period_kind = (row.get("period_kind") or "annual").lower()
            metric_name = _normalize_metric_name(str(row.get("metric_name") or "unknown_metric"))
            metric_value = _safe_float(row.get("metric_value"))
            if period_end is None or metric_name in {"", "unknown_metric"}:
                continue
            connection.execute(
                """
                INSERT INTO financial_statements
                (symbol, statement_type, period_end, period_kind, metric_name, metric_value, currency, source, source_ref, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol, statement_type, period_end, period_kind, metric_name, source)
                DO UPDATE SET
                    metric_value = EXCLUDED.metric_value,
                    currency = EXCLUDED.currency,
                    source_ref = EXCLUDED.source_ref,
                    created_at = NOW()
                """,
                (
                    symbol.upper(),
                    statement_type,
                    date.fromisoformat(str(period_end)),
                    period_kind,
                    metric_name,
                    metric_value,
                    row.get("currency", "INR"),
                    row.get("source", "NSE/BSE filings"),
                    row.get("source_ref"),
                ),
            )
            inserted += 1
    return inserted


def ingest_financial_results(symbols: list[str] | None = None) -> dict[str, Any]:
    targets = [s.upper() for s in (symbols or [])]
    if not targets:
        return {"status": "skipped", "imported": 0, "reason": "no symbols supplied"}
    imported = 0
    for symbol in targets:
        try:
            filings = _fetch_nse_financial_result_csv(symbol)
            rows: list[dict[str, Any]] = []
            for filing in filings[:12]:
                try:
                    rows.extend(_parse_xbrl_facts(symbol, filing))
                except (httpx.HTTPError, ET.ParseError, ValueError, KeyError):
                    continue
            imported += store_financial_statement_rows(symbol, rows)
        except (httpx.HTTPError, ValueError, KeyError):
            continue
    return {"status": "ok", "imported": imported, "symbols": len(targets)}


def parse_corporate_events(symbol: str, payload: list[dict[str, Any]]) -> int:
    if not payload:
        return 0
    with postgres_connection() as connection:
        inserted = 0
        for item in payload:
            event_date = item.get("event_date") or item.get("broadcastDate") or item.get("broadCastDate") or item.get("an_dt") or item.get("date")
            if not event_date:
                continue
            try:
                parsed_date = date.fromisoformat(str(event_date)[:10])
            except ValueError:
                try:
                    parsed_date = datetime.strptime(str(event_date)[:11].strip(), "%d-%b-%Y").date()
                except ValueError:
                    continue
            connection.execute(
                """
                INSERT INTO corporate_events
                (symbol, event_date, event_type, title, description, source, source_ref, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol, event_date, event_type, source_ref)
                DO UPDATE SET
                    title = COALESCE(EXCLUDED.title, corporate_events.title),
                    description = COALESCE(EXCLUDED.description, corporate_events.description)
                """,
                (
                    symbol.upper(),
                    parsed_date,
                    (item.get("event_type") or item.get("subject") or "announcement").upper(),
                    item.get("title") or item.get("subject") or item.get("attchmntText"),
                    item.get("description") or item.get("details") or item.get("desc"),
                    item.get("source", "NSE/BSE announcements"),
                    item.get("source_ref") or item.get("attchmntFile") or item.get("attachment"),
                ),
            )
            inserted += 1
    return inserted

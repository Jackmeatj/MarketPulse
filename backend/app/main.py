from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .storage import cached_json, init_storage, latest_overview, read_history, storage_health
from .derivatives import empty_derivatives
from .sectors import CORE_SECTORS, unavailable_sector
from .stocks import collect_sector_stocks

app = FastAPI(
    title="MarketPulse India API",
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

class MarketSnapshot(BaseModel):
    symbol: str
    name: str
    value: float
    change: float
    change_percent: float
    status: str
    timestamp: str | None = None
    source: str = "Unavailable"
    freshness: str = "unavailable"
    error: str | None = None
    market_state: str | None = None
    market_state_reason: str | None = None

class MarketOverview(BaseModel):
    as_of: str
    overall_signal: str
    score: int
    confidence: str
    global_markets: list[MarketSnapshot]
    global_exchanges: list[dict]
    macro: dict
    india_vix: MarketSnapshot
    breadth: dict
    gift_nifty: MarketSnapshot
    nifty50: MarketSnapshot
    bank_nifty: MarketSnapshot
    factors: list[dict]


@app.on_event("startup")
def startup() -> None:
    try:
        init_storage()
    except Exception:
        pass

def build_overview() -> MarketOverview:
    # Demo values only. These are intentionally not presented as live market data.
    # The next data-engineering stage will replace these values with collectors.
    nasdaq = MarketSnapshot(
        symbol="NASDAQ",
        name="Nasdaq Composite",
        value=21874.12,
        change=182.44,
        change_percent=0.84,
        status="positive",
    )
    dow = MarketSnapshot(
        symbol="DOW",
        name="Dow Jones",
        value=44901.26,
        change=174.52,
        change_percent=0.39,
        status="positive",
    )
    vix = MarketSnapshot(
        symbol="INDIA VIX",
        name="India VIX",
        value=13.42,
        change=-0.38,
        change_percent=-2.75,
        status="positive",
    )
    gift = MarketSnapshot(
        symbol="GIFT NIFTY",
        name="GIFT NIFTY",
        value=24862.50,
        change=118.50,
        change_percent=0.48,
        status="positive",
    )
    nifty = MarketSnapshot(
        symbol="NIFTY 50",
        name="NIFTY 50",
        value=24842.10,
        change=176.25,
        change_percent=0.71,
        status="positive",
    )
    bank = MarketSnapshot(
        symbol="BANK NIFTY",
        name="NIFTY Bank",
        value=56082.35,
        change=468.10,
        change_percent=0.84,
        status="positive",
    )

    advances = 1842
    declines = 913
    unchanged = 126
    ratio = round(advances / declines, 2)

    # Current product rule requested by the project:
    # VIX > 15 => positive, VIX <= 15 => negative.
    # This is a project-specific heuristic, not a conventional market rule.
    factors = [
        {
            "label": "Nasdaq",
            "value": f"{nasdaq.change_percent:+.2f}%",
            "signal": "positive" if nasdaq.change_percent >= 0 else "negative",
            "detail": "Global technology-market cue",
        },
        {
            "label": "Dow Jones",
            "value": f"{dow.change_percent:+.2f}%",
            "signal": "positive" if dow.change_percent >= 0 else "negative",
            "detail": "US blue-chip market cue",
        },
        {
            "label": "India VIX",
            "value": f"{vix.value:.2f}",
            "signal": "positive" if vix.value > 15 else "negative",
            "detail": "Using your current VIX rule",
        },
        {
            "label": "Market Breadth",
            "value": f"{ratio:.2f}x",
            "signal": "positive" if advances >= declines else "negative",
            "detail": "Advances vs declines",
        },
        {
            "label": "GIFT NIFTY",
            "value": f"{gift.change_percent:+.2f}%",
            "signal": "positive" if gift.change_percent >= 0 else "negative",
            "detail": "Pre-market indication",
        },
    ]

    positive = sum(1 for f in factors if f["signal"] == "positive")
    score = round(positive / len(factors) * 100)
    overall = "BULLISH" if score >= 60 else "BEARISH" if score <= 40 else "NEUTRAL"
    confidence = "High" if score in (0, 20, 80, 100) else "Moderate"

    return MarketOverview(
        as_of=datetime.now(timezone.utc).isoformat(),
        overall_signal=overall,
        score=score,
        confidence=confidence,
        global_markets=[nasdaq, dow],
        india_vix=vix,
        breadth={
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "ratio": ratio,
            "status": "positive" if advances >= declines else "negative",
        },
        gift_nifty=gift,
        nifty50=nifty,
        bank_nifty=bank,
        factors=factors,
    )

@app.get("/")
def root():
    return {
        "application": "MarketPulse India",
        "status": "running",
        "version": "0.4.0",
    }

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/api/market/overview", response_model=MarketOverview)
def market_overview():
    overview = latest_overview()
    if not overview:
        raise HTTPException(status_code=503, detail="Collector has not produced an overview yet")
    return overview


@app.get("/api/market/history")
def market_history(limit: int = 24):
    return {"items": read_history(limit)}


@app.get("/api/derivatives/options")
def options_chain(symbol: str = "NIFTY"):
    options = cached_json(f"marketpulse:latest:options:{symbol}")
    return options or empty_derivatives(symbol, "No stored options snapshot is available")


@app.get("/api/recommendation")
def recommendation(symbol: str = "NIFTY"):
    recommendation_data = cached_json(f"marketpulse:latest:recommendation:{symbol}")
    return recommendation_data or {
        "bias": "NEUTRAL",
        "market_score": None,
        "derivatives_signal": "UNAVAILABLE",
        "setups": [],
        "disclaimer": "No stored recommendation is available yet.",
    }


@app.get("/health/storage")
def health_storage():
    return storage_health()


@app.get("/api/sectors")
def sectors():
    sector_data = cached_json("marketpulse:latest:sectors")
    return sector_data or {
        "as_of": None,
        "benchmark": {"name": "NIFTY 50", "change_percent": None},
        "source": "Unavailable",
        "freshness": "unavailable",
        "items": [unavailable_sector(name, index_name, "No stored sector snapshot is available") for name, index_name in CORE_SECTORS.items()],
        "rotation": {"leaders": [], "improving": [], "weak": list(CORE_SECTORS)[:4]},
        "limitations": ["Collector has not produced a sector snapshot yet."],
    }


@app.get("/api/sectors/{sector}/stocks")
def sector_stocks(sector: str):
    sector_data = cached_json("marketpulse:latest:sectors") or {}
    sector_item = next((item for item in sector_data.get("items", []) if item.get("sector", "").lower() == sector.lower()), None)
    overview = latest_overview() or {}
    benchmark_return = (sector_data.get("benchmark") or {}).get("change_percent") or 0
    market_direction = overview.get("overall_signal", "NEUTRAL")
    result = collect_sector_stocks(sector, (sector_item or {}).get("change_percent") or 0, benchmark_return, market_direction)
    if not result.get("items") and sector not in CORE_SECTORS:
        raise HTTPException(status_code=404, detail="Unknown sector")
    return result

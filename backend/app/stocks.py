from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from math import sqrt
from statistics import mean, pstdev
from typing import Any
from urllib.parse import quote

import httpx

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
USER_AGENT = "Mozilla/5.0 (MarketPulse/0.6)"

SECTOR_STOCKS: dict[str, list[str]] = {
    "Auto": ["MARUTI", "M&M", "TATAMOTORS", "EICHERMOT", "BAJAJ-AUTO", "HEROMOTOCO", "TVSMOTOR", "ASHOKLEY", "BHARATFORG", "BOSCHLTD", "MOTHERSON", "SONACOMS", "EXIDEIND", "TIINDIA", "UNOMINDA", "ENDURANCE", "MOTHERSON", "APOLLOTYRE", "MRF", "BALKRISIND"],
    "Bank": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK", "BANKBARODA", "PNB", "IDFCFIRSTB", "CANBK", "FEDERALBNK", "AUBANK", "BANDHANBNK", "RBLBANK", "YESBANK", "IDBI", "IOB", "MAHABANK", "UNIONBANK", "INDIANB"],
    "Financial Services": ["BAJFINANCE", "BAJAJFINSV", "SHRIRAMFIN", "CHOLAFIN", "PFC", "RECLTD", "JIOFIN", "MUTHOOTFIN", "LICHSGFIN", "HDFCLIFE", "SBILIFE", "ICICIPRULI", "ICICIGI", "SBICARD", "MFSL", "MANAPPURAM", "MFIN", "ABCAPITAL", "CANFINHOME", "HUDCO"],
    "IT": ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "LTIM", "MPHASIS", "PERSISTENT", "COFORGE", "LTTS", "OFSS", "KPITTECH", "TATAELXSI", "CYIENT", "TATATECH", "HAPPSTMNDS", "BIRLASOFT", "SONATSOFTW", "INTELLECT", "ZENSARTECH", "BSOFT", "ECLERX", "NEWGEN", "RATEGAIN", "NIITLTD"],
    "Pharma": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "MANKIND", "TORNTPHARM", "LUPIN", "AUROPHARMA", "ZYDUSLIFE", "ALKEM", "BIOCON", "GLAND", "LAURUSLABS", "GLENMARK", "IPCALAB", "ABBOTINDIA", "NATCOPHARM", "GRANULES", "AJANTPHARM", "ERIS"],
    "Healthcare": ["APOLLOHOSP", "MAXHEALTH", "FORTIS", "LALPATHLAB", "METROPOLIS", "RAINBOW", "KIMS", "MEDANTA", "JUPITER", "YATHARTH", "GLOBALHEALTH", "SYNGENE", "POLYMED", "SOBHA", "STARHEALTH"],
    "FMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "TATACONSUM", "DABUR", "GODREJCP", "MARICO", "COLPAL", "UBL", "VBL", "UNITDSPR", "EMAMILTD", "JUBLFOOD", "PGHH", "RADICO", "BIKAJI", "PATANJALI", "CCL", "HATSUN"],
    "Metal": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "JINDALSTEL", "COALINDIA", "NMDC", "SAIL", "NATIONALUM", "HINDZINC", "APLAPOLLO", "RATNAMANI", "WELCORP", "MOIL", "HINDCOPPER", "JSL", "ADANIENT", "JINDALSAW", "GPIL", "MAITHANALL"],
    "Realty": ["DLF", "LODHA", "GODREJPROP", "OBEROIRLTY", "PHOENIXLTD", "PRESTIGE", "BRIGADE", "SOBHA", "SUNTECK", "ANANTRAJ", "SIGNATURE", "KOLTEPATIL", "MAHLIFE", "RUSTOMJEE", "IBREALEST", "RAYMOND", "ARVSMART", "EMBASSY", "BROOKFIELD", "INDIABULLS"],
    "PSU Bank": ["SBIN", "BANKBARODA", "PNB", "CANBK", "UNIONBANK", "INDIANB", "BANKINDIA", "MAHABANK", "IOB", "UCOBANK", "CENTRALBK", "PSB", "J&KBANK", "SURYODAY", "JAMNAAUTO"],
    "Private Bank": ["HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "INDUSINDBK", "IDFCFIRSTB", "FEDERALBNK", "RBLBANK", "BANDHANBNK", "YESBANK", "KARURVYSYA", "DCBBANK", "CSBBANK", "EQUITASBNK", "UJJIVANSFB", "SOUTHBANK", "CUB", "TMB", "KTKBANK", "DHANBANK"],
    "Oil & Gas": ["RELIANCE", "ONGC", "IOC", "BPCL", "GAIL", "HINDPETRO", "OIL", "PETRONET", "IGL", "MGL", "GUJGASLTD", "ATGL", "AEGISLOG", "CASTROLIND", "CHENNPETRO", "MRPL", "GSPL", "BORORENEW", "FINEORG", "KALYANKJIL"],
    "Power": ["NTPC", "POWERGRID", "ADANIGREEN", "TATAPOWER", "JSWENERGY", "ADANIENSOL", "TORNTPOWER", "NHPC", "SJVN", "NLCINDIA", "CESC", "RPOWER", "INOXWIND", "SUZLON", "WAAREEENER", "KPI GREEN", "JPPOWER", "RPOWER", "GMRINFRA", "IREDA"],
    "Consumer Durables": ["TITAN", "HAVELLS", "VOLTAS", "DIXON", "KAYNES", "AMBER", "WHIRLPOOL", "CROMPTON", "VGUARD", "BLUESTARCO", "VOLTAMP", "RAJESHEXPO", "KAJARIACER", "CENTURYPLY", "BATAINDIA", "RELAXO", "CAMPUS", "METROBRAND", "PGEL", "IFBIND"],
    "Capital Goods": ["LT", "SIEMENS", "ABB", "BEL", "HAL", "BHEL", "CGPOWER", "BEML", "THERMAX", "CUMMINSIND", "POLYCAB", "KEI", "KALPATPOWR", "TRIVENI", "GRAPHITE", "ELGIEQUIP", "AIAENG", "ENGINERSIN", "KIRLOSBROS", "BDL"],
    "Cement": ["ULTRACEMCO", "GRASIM", "SHREECEM", "AMBUJACEM", "ACC", "DALBHARAT", "JKCEMENT", "RAMCOCEM", "JKLAKSHMI", "NUVOCO", "BIRLACORPN", "HEIDELBERG", "PRISMJOHN", "STARCEMENT", "ORIENTCEM", "SAGCEM", "INDIACEM", "SANGHIIND", "EVERESTIND", "NCLIND"],
    "Chemicals": ["PIDILITIND", "SRF", "UPL", "AARTIIND", "DEEPAKNTR", "NAVINFLUOR", "ATUL", "CLEAN", "FINEORG", "BALRAMCHIN", "PIIND", "TATACHEM", "GUJALKALI", "ROSSARI", "ALKYLAMINE", "NOCIL", "ANUPAMRASAYAN", "EPL", "JUBLINGREA", "VINATIORGA"],
    "Media": ["SUNTV", "ZEEL", "PVRINOX", "NAZARA", "SAREGAMA", "NETWORK18", "TV18BRDCST", "TIPSINDLTD", "DBCORP", "JAGRAN", "HATHWAY", "DEN", "HINDUSTANMEDIA", "HTMEDIA", "MPSLTD", "TIPSFILMS", "WONDERLA", "INOXWIND", "DISHTV", "ORIENTHOT"],
    "Telecommunications": ["BHARTIARTL", "INDUSTOWER", "TATACOMM", "IDEA", "ROUTE", "HFCL", "TEJASNET", "TANLA", "MOBIKWIK", "NETWORK18", "ITI", "RAILTEL", "GTLINFRA", "STLTECH", "NELCO"],
    "Construction": ["LT", "ADANIPORTS", "RVNL", "IRCON", "NBCC", "NCC", "KEC", "KNRCON", "ASHOKA", "HG infra", "PNCINFRA", "HGINFRA", "GRINFRA", "IRB", "GPPL", "CONCOR", "MAZDOCK", "COCHINSHIP", "GMRAIRPORT", "ENGINERSIN"],
}


def yahoo_history(symbol: str) -> dict[str, Any]:
    response = httpx.get(YAHOO_CHART_URL.format(symbol=quote(symbol + ".NS")), params={"range": "3mo", "interval": "1d"}, headers={"User-Agent": USER_AGENT}, timeout=12)
    response.raise_for_status()
    result = response.json()["chart"]["result"][0]
    meta = result["meta"]
    quote_data = result["indicators"]["quote"][0]
    closes = [float(value) for value in quote_data["close"] if value is not None]
    highs = [float(value) for value in quote_data["high"] if value is not None]
    lows = [float(value) for value in quote_data["low"] if value is not None]
    volumes = [float(value) for value in quote_data["volume"] if value is not None]
    if len(closes) < 20:
        raise ValueError("Insufficient daily candle history")
    return {"symbol": symbol, "close": closes[-1], "previous": closes[-2], "closes": closes, "highs": highs, "lows": lows, "volumes": volumes, "timestamp": datetime.fromtimestamp(meta.get("regularMarketTime", result["timestamp"][-1]), timezone.utc).isoformat(), "source": f"Yahoo Finance ({symbol}.NS)"}


def ema(values: list[float], period: int) -> float:
    result = values[0]
    multiplier = 2 / (period + 1)
    for value in values[1:]:
        result = (value - result) * multiplier + result
    return result


def rsi(values: list[float], period: int = 14) -> float:
    changes = [values[index] - values[index - 1] for index in range(1, len(values))][-period:]
    gains = [change for change in changes if change > 0]
    losses = [-change for change in changes if change < 0]
    average_gain = sum(gains) / period
    average_loss = sum(losses) / period
    if average_loss == 0:
        return 100.0
    return 100 - (100 / (1 + average_gain / average_loss))


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    if len(highs) != len(lows) or len(lows) != len(closes) or len(closes) <= period:
        return None
    true_ranges = [
        max(highs[index] - lows[index], abs(highs[index] - closes[index - 1]), abs(lows[index] - closes[index - 1]))
        for index in range(1, len(closes))
    ]
    return mean(true_ranges[-period:]) if len(true_ranges) >= period else None


def stock_metrics(symbol: str, sector_return: float, benchmark_return: float, market_direction: str) -> dict[str, Any] | None:
    try:
        history = yahoo_history(symbol)
        closes = history["closes"]
        highs = history["highs"]
        lows = history["lows"]
        returns = [(closes[index] / closes[index - 1] - 1) * 100 for index in range(1, len(closes))]
        change_1d = (closes[-1] / closes[-2] - 1) * 100
        change_5d = (closes[-1] / closes[-6] - 1) * 100
        change_20d = (closes[-1] / closes[-21] - 1) * 100
        relative_strength = change_20d - benchmark_return
        trend_score = max(0, min(100, round(50 + (closes[-1] / ema(closes[-20:], 20) - 1) * 500)))
        momentum_score = max(0, min(100, round(50 + rsi(closes) / 2 + change_5d * 3)))
        volume_ratio = history["volumes"][-1] / mean(history["volumes"][-20:]) if history["volumes"] else 1
        liquidity = max(0, min(100, round(50 + (volume_ratio - 1) * 35)))
        volatility = pstdev(returns[-20:]) * sqrt(252)
        volatility_score = max(0, min(100, round(100 - volatility * 4)))
        velocity = (closes[-1] - closes[-6]) / 5
        vwap_window = min(len(closes), 20)
        vwap_volume = sum(history["volumes"][-vwap_window:])
        vwap = sum(close * volume for close, volume in zip(closes[-vwap_window:], history["volumes"][-vwap_window:])) / vwap_volume if vwap_volume else None
        macd = ema(closes, 12) - ema(closes, 26) if len(closes) >= 26 else None
        atr_value = atr(highs, lows, closes)
        score = round(trend_score * .25 + momentum_score * .25 + max(0, min(100, 50 + relative_strength * 3)) * .2 + liquidity * .1 + volatility_score * .1 + (65 if change_1d >= sector_return else 35) * .1)
        support = min(closes[-20:])
        resistance = max(closes[-20:])
        action = "Breakout" if closes[-1] >= resistance * .995 else "Reversal" if change_1d * change_5d < 0 else "Trend continuation"
        return {"symbol": symbol, "sector_alignment": round(change_1d - sector_return, 2), "market_direction": market_direction, "price": history["close"], "change_percent": round(change_1d, 2), "trend": trend_score, "strength": round(max(0, min(100, 50 + relative_strength * 3))), "momentum": momentum_score, "volume": round(volume_ratio, 2), "velocity": round(velocity, 2), "relative_strength": round(relative_strength, 2), "liquidity": liquidity, "volatility": round(volatility, 2), "support": round(support, 2), "resistance": round(resistance, 2), "price_action": action, "ema_20": round(ema(closes, 20), 2), "ema_50": round(ema(closes, 50), 2), "ema_200": round(ema(closes, 200), 2), "rsi": round(rsi(closes), 2), "macd": round(macd, 2) if macd is not None else None, "vwap": round(vwap, 2) if vwap is not None else None, "atr": round(atr_value, 2) if atr_value is not None else None, "score": score, "timestamp": history["timestamp"], "source": history["source"], "freshness": "live"}
    except Exception:
        return None


def collect_sector_stocks(sector: str, sector_return: float = 0, benchmark_return: float = 0, market_direction: str = "NEUTRAL") -> dict[str, Any]:
    symbols = SECTOR_STOCKS.get(sector)
    if not symbols:
        return {"sector": sector, "items": [], "freshness": "unavailable", "source": "No configured sector universe", "error": "Unknown sector"}
    unique_symbols = list(dict.fromkeys(symbols))
    with ThreadPoolExecutor(max_workers=8) as executor:
        items = list(executor.map(lambda symbol: stock_metrics(symbol, sector_return, benchmark_return, market_direction), unique_symbols))
    ranked = sorted((item for item in items if item), key=lambda item: item["score"], reverse=True)[:20]
    return {"sector": sector, "items": ranked, "freshness": "live" if ranked else "unavailable", "source": "Yahoo Finance daily candles; curated NSE sector universe", "as_of": datetime.now(timezone.utc).isoformat(), "limitations": ["Top stocks are ranked from the configured sector universe.", "Support/resistance and technical scores use the available three-month daily candle window."]}

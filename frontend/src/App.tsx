import { useEffect, useMemo, useState } from "react"
import "./App.css"

type Signal = "positive" | "negative" | "neutral"
type Freshness = "live" | "stale" | "unavailable"

type HistoryItem = {
  timestamp: string
  signal: string
  score: number
  confidence: string
}

type Derivatives = {
  symbol: string
  timestamp: string | null
  source: string
  freshness: Freshness
  underlying_value: number | null
  atm_strike?: number
  atm_iv?: { call: number | null; put: number | null }
  pcr: number | null
  max_pain: number | null
  support: number | null
  resistance: number | null
  signal: string
  error: string | null
  expiry?: string
  totals?: {
    call_oi: number
    put_oi: number
    call_change_oi: number
    put_change_oi: number
  }
}

type Recommendation = {
  symbol?: string
  bias: string
  classification?: string
  overall_score?: number | null
  investment_score?: number | null
  trading_score?: number | null
  market_score: number
  derivatives_signal: string
  leading_sector?: string | null
  scores?: Record<string, number | null>
  thesis?: string[]
  catalysts?: string[]
  risks?: string[]
  data_quality?: { status: string; available_engines: number; pending_engines: number; missing_inputs: string[] }
  setups: { instrument: string; direction: string; trigger: string; risk: string; reason: string }[]
  disclaimer: string
}

const recommendationScoreLabels: Record<string, string> = {
  fundamentals: "Fundamentals",
  growth: "Growth acceleration",
  sector: "Sector strength",
  technical: "Technical structure",
  relative_strength: "Relative strength",
  volume: "Volume & velocity",
  catalyst: "Catalysts",
  valuation: "Valuation",
  risk: "Risk control",
  derivatives: "Derivatives",
}

type SectorItem = {
  sector: string
  index_name: string
  value: number | null
  change_percent: number | null
  relative_strength: number | null
  score: number | null
  classification: string
  trend_score: number | null
  momentum_score: number | null
  breadth_score: number | null
  advances: number | null
  declines: number | null
  unchanged: number | null
  timestamp: string | null
  source: string
  freshness: Freshness
  error?: string
}

type SectorData = {
  as_of: string
  benchmark: { name: string; change_percent: number | null }
  source: string
  freshness: Freshness
  items: SectorItem[]
  rotation: { leaders: string[]; improving: string[]; weak: string[] }
  limitations: string[]
}

type StockMetric = {
  symbol: string
  sector_alignment: number
  market_direction: string
  price: number
  change_percent: number
  trend: number
  strength: number
  momentum: number
  volume: number
  velocity: number
  relative_strength: number
  liquidity: number
  volatility: number
  support: number
  resistance: number
  price_action: string
  score: number
  timestamp: string
  source: string
  freshness: Freshness
}

type SectorStocks = {
  sector: string
  items: StockMetric[]
  freshness: Freshness
  source: string
  as_of: string
  limitations: string[]
  error?: string
}

type StockAnalysis = {
  symbol: string
  sector: string
  as_of: string
  price: number
  change_percent: number
  overall_score: number
  investment_score: number
  trading_score: number
  classification: string
  decision: string
  scores: Record<string, number | null>
  technical: Record<string, number | string>
  fundamentals: Record<string, number | null>
  thesis: string[]
  catalysts: string[]
  risks: string[]
  data_quality: { status: string; available_engines: number; pending_engines: number; missing_inputs: string[] }
  sources: string[]
  disclaimer: string
}

type Macro = {
  dollar_index: Snapshot
  fed_funds_rate: { value: number | null; next_revision_date: string | null; source: string; freshness: Freshness }
  us_treasury_10y: Snapshot
  institutional_flow: { fii_net: number | null; dii_net: number | null; timestamp: string | null; source: string; freshness: Freshness }
}

type Snapshot = {
  symbol: string
  name: string
  value: number
  change: number
  change_percent: number
  status: Signal
  timestamp: string | null
  source: string
  freshness: Freshness
  error?: string
  market_state?: "active" | "offline"
  market_state_reason?: string
}

type Overview = {
  as_of: string
  overall_signal: string
  score: number
  confidence: string
  global_markets: Snapshot[]
  global_exchanges: (Snapshot & { country: string })[]
  macro: Macro
  india_vix: Snapshot
  breadth: {
    advances: number
    declines: number
    unchanged: number
    ratio: number
    status: Signal
    timestamp: string | null
    source: string
    freshness: Freshness
    error?: string
  }
  gift_nifty: Snapshot
  nifty50: Snapshot
  bank_nifty: Snapshot
  factors: {
    label: string
    value: string
    signal: Signal
    detail: string
  }[]
}

const API_URL = import.meta.env.VITE_API_URL || ""

function formatNumber(value: number, decimals = 2) {
  return value.toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

function pct(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`
}

function SignalDot({ signal }: { signal: Signal }) {
  return <span className={`signal-dot ${signal}`} />
}

function InfoTip({ text }: { text: string }) {
  return <span className="info-tip"><button type="button" aria-label="More information">i</button><span>{text}</span></span>
}

function MarketCard({
  title,
  subtitle,
  snapshot,
  featured = false,
}: {
  title: string
  subtitle: string
  snapshot: Snapshot
  featured?: boolean
}) {
  const offline = snapshot.market_state === "offline"
  return (
    <article className={`metric-card ${featured ? "featured" : ""} ${offline ? "offline" : ""}`}>
      <div className="metric-top">
        <div>
          <div className="metric-title">{title}</div>
          <div className="metric-subtitle">{subtitle}</div>
        </div>
        <div className="metric-actions"><SignalDot signal={offline ? "neutral" : snapshot.status} /><InfoTip text={offline ? `${snapshot.market_state_reason}. Last provider quote: ${snapshot.timestamp || "unavailable"}.` : `${snapshot.source}. Updated ${snapshot.timestamp || "unavailable"}.`} /></div>
      </div>

      <div className="metric-value">{snapshot.freshness === "unavailable" ? "Unavailable" : formatNumber(snapshot.value)}</div>

      <div className={`metric-change ${snapshot.status}`}>
        {snapshot.change >= 0 ? "▲" : "▼"} {formatNumber(Math.abs(snapshot.change))}{" "}
        <span>{pct(snapshot.change_percent)}</span>
      </div>
    </article>
  )
}

function StockAnalysisPage({ symbol, sector, onBack }: { symbol: string; sector: string; onBack: () => void }) {
  const [analysis, setAnalysis] = useState<StockAnalysis | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    fetch(`${API_URL}/api/stocks/${encodeURIComponent(symbol)}/analysis?sector=${encodeURIComponent(sector)}`)
      .then((response) => { if (!response.ok) throw new Error(`API returned ${response.status}`); return response.json() as Promise<StockAnalysis> })
      .then(setAnalysis)
      .catch((err: Error) => setError(err.message))
  }, [sector, symbol])

  return <div className="app">
    <header className="topbar"><div className="brand"><div className="brand-mark">M</div><div><div className="brand-name">MarketPulse</div><div className="brand-subtitle">STOCK INTELLIGENCE</div></div></div><button className="menu-button" type="button" onClick={onBack}>Back to {sector}</button></header>
    <main className="dashboard stock-analysis-page">
      <div className="detail-crumb"><button type="button" onClick={onBack}>Indian sectors</button><span>/</span><button type="button" onClick={onBack}>{sector}</button><span>/</span><strong>{symbol}</strong></div>
      {!analysis && !error && <div className="empty-state">Calculating stock intelligence...</div>}
      {error && <div className="error-box"><strong>Stock analysis unavailable</strong><span>{error}</span></div>}
      {analysis && <>
        <section className={`decision-banner ${analysis.decision.includes("WATCH") ? "positive" : "neutral"}`}>
          <div><span className="section-kicker">MARKETPULSE RECOMMENDATION ENGINE</span><h1>{analysis.symbol}</h1><p>{analysis.sector} · ₹{formatNumber(analysis.price)} · {pct(analysis.change_percent)}</p></div>
          <div className="decision-score"><strong>{analysis.overall_score}</strong><span>/ 100</span><b>{analysis.decision}</b><small>{analysis.classification.replaceAll("_", " ")}</small></div>
        </section>
        <div className="analysis-score-strip"><div><span>Investment score</span><strong>{analysis.investment_score}</strong><small>Company quality & opportunity</small></div><div><span>Trading score</span><strong>{analysis.trading_score}</strong><small>Price, momentum & participation</small></div><div><span>Data status</span><strong>{analysis.data_quality.status}</strong><small>{analysis.data_quality.available_engines} engines available · {analysis.data_quality.pending_engines} pending</small></div></div>
        <section className="analysis-section"><div className="section-heading"><div><span className="section-kicker">01 / ENGINE BREAKDOWN</span><h2>Evidence behind the decision</h2></div></div><div className="analysis-factor-grid">{Object.entries(recommendationScoreLabels).filter(([key]) => key !== "derivatives").map(([key, label]) => <div className="analysis-factor" key={key}><span>{label}</span><strong>{analysis.scores[key] ?? "PENDING"}</strong>{analysis.scores[key] !== null && <i><em style={{ width: `${analysis.scores[key]}%` }} /></i>}</div>)}</div></section>
        <section className="analysis-columns"><article className="analysis-section"><span className="section-kicker">02 / THESIS</span><h2>Why it qualifies</h2>{analysis.thesis.map((item) => <p className="analysis-copy" key={item}>{item}</p>)}</article><article className="analysis-section"><span className="section-kicker">03 / RISK GATE</span><h2>What can invalidate it</h2>{analysis.risks.map((item) => <p className="analysis-copy risk-copy" key={item}>{item}</p>)}</article></section>
        <section className="analysis-section"><span className="section-kicker">04 / PRICE STRUCTURE</span><h2>Technical parameters</h2><div className="technical-grid">{Object.entries(analysis.technical).map(([key, value]) => <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{typeof value === "number" ? value.toLocaleString("en-IN") : value}</strong></div>)}</div></section>
        <section className="analysis-section"><span className="section-kicker">05 / FUNDAMENTAL ENGINE</span><h2>Financial quality & valuation</h2><div className="technical-grid">{Object.entries(analysis.fundamentals).map(([key, value]) => <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{value === null ? "PENDING" : value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</strong></div>)}</div></section>
        <small className="sector-limitations">Sources: {analysis.sources.join(" · ")}. {analysis.disclaimer}</small>
      </>}
    </main>
  </div>
}

function SectorStocksPage({ sector, onBack }: { sector: string; onBack: () => void }) {
  const [data, setData] = useState<SectorStocks | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    fetch(`${API_URL}/api/sectors/${encodeURIComponent(sector)}/stocks`)
      .then((response) => response.json() as Promise<SectorStocks>)
      .then(setData)
      .catch((err: Error) => setError(err.message))
  }, [sector])

  const openStock = (symbol: string) => {
    window.history.pushState({}, "", `/stocks/${encodeURIComponent(symbol)}/analysis?sector=${encodeURIComponent(sector)}`)
    window.dispatchEvent(new PopStateEvent("popstate"))
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><div className="brand-mark">M</div><div><div className="brand-name">MarketPulse</div><div className="brand-subtitle">SECTOR STOCK RADAR</div></div></div>
        <button className="menu-button" type="button" onClick={onBack}>Back to sectors</button>
      </header>
      <main className="dashboard">
        <div className="detail-crumb"><button type="button" onClick={onBack}>Indian sectors</button><span>/</span><strong>{sector}</strong></div>
        <section className="detail-hero"><div><span className="section-kicker">SECTOR DRILL-DOWN</span><h1>{sector}</h1><p>Top stocks ranked by technical trend, momentum, relative strength, liquidity, and price action.</p></div><span className={`data-status ${data?.freshness === "live" ? "live" : "stale"}`}><span className="status-dot" /> {data?.freshness === "live" ? "LIVE" : "UNAVAILABLE"}</span></section>
        {error && <div className="error-box"><strong>Stock data unavailable</strong><span>{error}</span></div>}
        {!data && !error && <div className="empty-state">Loading sector constituents...</div>}
        {data && data.items.length > 0 && <section className="stock-table-wrap">
          <div className="stock-table stock-table-head"><span># / Stock</span><span>Score</span><span>Price</span><span>Trend</span><span>Momentum</span><span>RS</span><span>Volume</span><span>Liquidity</span><span>Action</span></div>
          {data.items.map((stock, index) => <div className="stock-table stock-row" key={stock.symbol}><span><button className="stock-link" type="button" onClick={() => openStock(stock.symbol)}><strong>{String(index + 1).padStart(2, "0")} · {stock.symbol}</strong></button><small>{stock.freshness.toUpperCase()} · {new Date(stock.timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}</small></span><strong className="sector-score">{stock.score}</strong><span>{formatNumber(stock.price)}</span><span>{stock.trend}</span><span>{stock.momentum}</span><span className={stock.relative_strength >= 0 ? "positive-text" : "negative-text"}>{pct(stock.relative_strength)}</span><span>{stock.volume}x</span><span>{stock.liquidity}</span><span className="price-action"><strong>{stock.price_action}</strong><small>S {formatNumber(stock.support)} · R {formatNumber(stock.resistance)}</small></span></div>)}
        </section>}
        {data && <small className="sector-limitations">{data.source}. {data.limitations.join(" ")}</small>}
      </main>
    </div>
  )
}

type AppAppearance = "glass" | "basic" | "aurora" | "sunset"
type FontPreset = "balanced" | "compact" | "wide"

const appearanceOptions: { value: AppAppearance; label: string }[] = [
  { value: "glass", label: "Glass" },
  { value: "basic", label: "Slate" },
  { value: "aurora", label: "Aurora" },
  { value: "sunset", label: "Sunset" },
]

const fontOptions: { value: FontPreset; label: string }[] = [
  { value: "balanced", label: "Balanced" },
  { value: "compact", label: "Compact" },
  { value: "wide", label: "Wide" },
]

function App() {
  const [data, setData] = useState<Overview | null>(null)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [derivatives, setDerivatives] = useState<Derivatives | null>(null)
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null)
  const [sectors, setSectors] = useState<SectorData | null>(null)
  const [appearance, setAppearance] = useState<AppAppearance>("glass")
  const [fontPreset, setFontPreset] = useState<FontPreset>("balanced")
  const [menuOpen, setMenuOpen] = useState(false)
  const [selectedSector, setSelectedSector] = useState<string | null>(() => {
    const match = window.location.pathname.match(/^\/sectors\/([^/]+)\/stocks$/)
    return match ? decodeURIComponent(match[1]) : null
  })
  const [selectedStock, setSelectedStock] = useState<{ symbol: string; sector: string } | null>(() => {
    const match = window.location.pathname.match(/^\/stocks\/([^/]+)\/analysis$/)
    const sector = new URLSearchParams(window.location.search).get("sector")
    return match && sector ? { symbol: decodeURIComponent(match[1]), sector } : null
  })

  useEffect(() => {
    const syncRoute = () => {
      const stockMatch = window.location.pathname.match(/^\/stocks\/([^/]+)\/analysis$/)
      const sector = new URLSearchParams(window.location.search).get("sector")
      setSelectedStock(stockMatch && sector ? { symbol: decodeURIComponent(stockMatch[1]), sector } : null)
    }
    window.addEventListener("popstate", syncRoute)
    return () => window.removeEventListener("popstate", syncRoute)
  }, [])

  const openSector = (sector: string) => {
    window.history.pushState({}, "", `/sectors/${encodeURIComponent(sector)}/stocks`)
    setSelectedSector(sector)
  }

  useEffect(() => {
    let active = true

    const load = () => Promise.all([
      fetch(`${API_URL}/api/market/overview`).then((response) => {
        if (!response.ok) throw new Error(`API returned ${response.status}`)
        return response.json() as Promise<Overview>
      }),
      fetch(`${API_URL}/api/market/history`).then((response) => response.json() as Promise<{ items: HistoryItem[] }>),
      fetch(`${API_URL}/api/derivatives/options`).then((response) => response.json() as Promise<Derivatives>),
      fetch(`${API_URL}/api/recommendation`).then((response) => response.json() as Promise<Recommendation>),
      fetch(`${API_URL}/api/sectors`).then((response) => response.json() as Promise<SectorData>),
    ])
      .then(([overview, timeline, options, setup, sectorData]) => {
        if (!active) return
        setData(overview)
        setHistory(timeline.items)
        setDerivatives(options)
        setRecommendation(setup)
        setSectors(sectorData)
        setError("")
      })
      .catch((err: Error) => {
        if (!active) return
        setError(err.message)
      })
      .finally(() => setLoading(false))

    load()
    const refresh = window.setInterval(load, 60_000)
    return () => {
      active = false
      window.clearInterval(refresh)
    }
  }, [])

  const breadthPercent = useMemo(() => {
    if (!data) return 0
    const total = data.breadth.advances + data.breadth.declines
    return total ? (data.breadth.advances / total) * 100 : 0
  }, [data])

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="loading-orb" />
        <div>Initializing MarketPulse...</div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="loading-screen">
        <div className="error-box">
          <strong>Market data unavailable</strong>
          <span>{error || "Unknown error"}</span>
          <small>API: {API_URL}</small>
        </div>
      </div>
    )
  }

  if (selectedStock) return <StockAnalysisPage symbol={selectedStock.symbol} sector={selectedStock.sector} onBack={() => { window.history.pushState({}, "", `/sectors/${encodeURIComponent(selectedStock.sector)}/stocks`); setSelectedStock(null); setSelectedSector(selectedStock.sector) }} />
  if (selectedSector) return <SectorStocksPage sector={selectedSector} onBack={() => { window.history.pushState({}, "", "/"); setSelectedSector(null) }} />

  const bullish = data.overall_signal === "BULLISH"
  const dataSources = [
    ...data.global_markets,
    data.india_vix,
    data.breadth,
    data.gift_nifty,
    data.nifty50,
    data.bank_nifty,
  ]
  const hasUnavailableSource = dataSources.some((item) => item.freshness === "unavailable")
  const hasStaleSource = dataSources.some((item) => item.freshness === "stale")
  const dashboardFreshness = hasUnavailableSource || hasStaleSource ? "stale" : "live"
  const updatedAt = new Date(data.as_of).toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })

  return (
    <div className={`app ${appearance} ${fontPreset}`}>
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">M</div>
          <div>
            <div className="brand-name">MarketPulse</div>
            <div className="brand-subtitle">INDIA MARKET INTELLIGENCE</div>
          </div>
        </div>

        <div className="topbar-right">
          <div className="live-pill">
            <span className="live-dot" />
            ENGINE ONLINE
          </div>
          <div className="timestamp">
            {new Date(data.as_of).toLocaleTimeString("en-IN", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </div>
          <div className="appearance-menu">
            <button className="menu-button" type="button" onClick={() => setMenuOpen(!menuOpen)} aria-expanded={menuOpen}>View</button>
            {menuOpen && (
              <div className="menu-popover">
                <span>Skin</span>
                {appearanceOptions.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className={appearance === option.value ? "selected" : ""}
                    onClick={() => { setAppearance(option.value); setMenuOpen(false) }}
                  >
                    {option.label}
                  </button>
                ))}
                <span>Font</span>
                {fontOptions.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className={fontPreset === option.value ? "selected" : ""}
                    onClick={() => { setFontPreset(option.value); setMenuOpen(false) }}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="dashboard">
        <section className={`signal-hero ${bullish ? "bullish" : "bearish"}`}>
          <div className="hero-copy">
            <div className="eyebrow">MARKET OPENING BIAS</div>
            <h1>{data.overall_signal}</h1>
            <p>
              A composite opening indicator built from global markets, India VIX,
              market breadth and GIFT NIFTY.
            </p>
            <div className="hero-tags">
              <span>Derivatives Intelligence</span>
              <span>Pre-Market Analysis</span>
            </div>
          </div>

          <div className="score-wrap">
            <div className="score-ring" style={{ "--score": `${data.score * 3.6}deg` } as React.CSSProperties}>
              <div className="score-inner">
                <strong>{data.score}</strong>
                <span>/ 100</span>
              </div>
            </div>
            <div className="score-label">{data.confidence} confidence</div>
          </div>
        </section>

        <div className="section-heading global-heading">
          <div>
            <span className="section-kicker">GLOBAL TAPE</span>
            <h2>Major exchanges & macro drivers</h2>
          </div>
          <span className="section-note">One view · provider timestamps</span>
        </div>

        <section className="global-panel">
          <div className="exchange-grid">
            {data.global_exchanges.map((market) => (
              <article className={`exchange-box ${market.market_state === "offline" ? "offline" : ""}`} key={market.symbol}>
                <div className="exchange-country">{market.country}</div>
                <div className="exchange-title"><strong>{market.symbol}</strong><InfoTip text={`${market.source}. ${market.market_state_reason || "Provider status unavailable"}.`} /></div>
                <span className={market.market_state === "offline" ? "neutral" : market.status}>{market.freshness === "unavailable" ? "Unavailable" : formatNumber(market.value)}</span>
                <small>{market.market_state === "offline" ? "OFFLINE · " + (market.market_state_reason || "Closed") : pct(market.change_percent)}</small>
              </article>
            ))}
          </div>
          <div className="macro-grid">
            <article className="macro-box"><span>Dollar Index</span><strong>{data.macro.dollar_index.freshness === "unavailable" ? "Unavailable" : formatNumber(data.macro.dollar_index.value)}</strong><small>{data.macro.dollar_index.source}</small></article>
            <article className="macro-box"><span>US Treasury 10Y</span><strong>{data.macro.us_treasury_10y.freshness === "unavailable" ? "Unavailable" : `${formatNumber(data.macro.us_treasury_10y.value)}%`}</strong><small>{data.macro.us_treasury_10y.source}</small></article>
            <article className="macro-box"><span>Fed Funds Rate</span><strong>{data.macro.fed_funds_rate.value === null ? "Unavailable" : `${data.macro.fed_funds_rate.value.toFixed(2)}%`}</strong><small>{data.macro.fed_funds_rate.next_revision_date ? `Next revision ${data.macro.fed_funds_rate.next_revision_date}` : "Configure trusted policy feed"}</small></article>
            <article className="macro-box"><span>Institutional Flow</span><strong>{data.macro.institutional_flow.fii_net === null ? "Unavailable" : `FII ${data.macro.institutional_flow.fii_net.toFixed(0)}`}</strong><small>{data.macro.institutional_flow.dii_net === null ? data.macro.institutional_flow.source : `DII ${data.macro.institutional_flow.dii_net.toFixed(0)}`}</small></article>
          </div>
        </section>

        <div className="section-heading">
          <div>
            <span className="section-kicker">02 / INDIAN SECTOR</span>
            <h2>Sector intelligence</h2>
          </div>
          <span className={`data-status ${sectors?.freshness === "live" ? "live" : "stale"}`}><span className="status-dot" /> {sectors?.freshness === "live" ? "NSE LIVE" : "NSE UNAVAILABLE"}</span>
        </div>

        <section className="sector-panel">
          <div className="rotation-strip">
            <div><span>LEADERS</span><strong>{sectors?.rotation.leaders.join(" · ") || "-"}</strong></div>
            <div><span>IMPROVING VS NIFTY</span><strong>{sectors?.rotation.improving.join(" · ") || "-"}</strong></div>
            <div><span>WEAK / UNAVAILABLE</span><strong>{sectors?.rotation.weak.join(" · ") || "-"}</strong></div>
          </div>
          <div className="sector-table-wrap">
            <div className="sector-table sector-table-head"><span>Sector</span><span>Score</span><span>1D</span><span>RS vs NIFTY</span><span>Trend</span><span>Breadth</span></div>
            {sectors?.items.map((sector) => (
              <button className={`sector-table sector-row ${sector.freshness === "unavailable" ? "offline" : ""}`} key={sector.sector} type="button" onClick={() => openSector(sector.sector)}>
                <span><strong>{sector.sector}</strong><small>{sector.index_name}</small></span>
                <span className="sector-score">{sector.score ?? "-"}</span>
                <span className={sector.change_percent && sector.change_percent >= 0 ? "positive-text" : "negative-text"}>{sector.change_percent === null ? "-" : pct(sector.change_percent)}</span>
                <span className={sector.relative_strength !== null && sector.relative_strength >= 0 ? "positive-text" : "negative-text"}>{sector.relative_strength === null ? "-" : pct(sector.relative_strength)}</span>
                <span>{sector.trend_score ?? "-"}</span>
                <span>{sector.breadth_score === null ? "Pending" : `${sector.breadth_score}%`}</span>
              </button>
            ))}
          </div>
          <small className="sector-limitations">{sectors?.limitations.join(" ")}</small>
        </section>

        <div className="section-heading">
          <div>
            <span className="section-kicker">01 / MARKET CUES</span>
            <h2>Global & Pre-Market</h2>
          </div>
          <span className={`data-status ${dashboardFreshness}`}>
            <span className="status-dot" />
            {dashboardFreshness === "live" ? "LIVE" : "STALE"}
            <span className="status-time">
              {dashboardFreshness === "live" ? `Updated ${updatedAt}` : "Source update required"}
            </span>
          </span>
        </div>

        <section className="metrics-grid">
          <MarketCard
            title="NASDAQ"
            subtitle="Nasdaq Composite"
            snapshot={data.global_markets[0]}
            featured
          />
          <MarketCard
            title="DOW JONES"
            subtitle="US Blue Chips"
            snapshot={data.global_markets[1]}
            featured
          />
          <MarketCard
            title="GIFT NIFTY"
            subtitle="Pre-market indication"
            snapshot={data.gift_nifty}
            featured
          />
          <MarketCard
            title="INDIA VIX"
            subtitle="Volatility index"
            snapshot={data.india_vix}
          />
        </section>

        <div className="section-heading">
          <div>
            <span className="section-kicker">03 / MARKET BREADTH</span>
            <h2>Participation</h2>
          </div>
        </div>

        <section className="breadth-layout">
          <article className="breadth-card">
            <div className="breadth-head">
              <div>
                <div className="metric-title">NSE ADVANCES / DECLINES</div>
                <div className="metric-subtitle">Market participation snapshot</div>
              </div>
              <div className={`signal-badge ${data.breadth.status}`}>
                <SignalDot signal={data.breadth.status} />
                {data.breadth.status === "positive" ? "BULLISH BREADTH" : "BEARISH BREADTH"}
              </div>
            </div>

            <div className="breadth-numbers">
              <div>
                <strong>{formatNumber(data.breadth.advances, 0)}</strong>
                <span>Advances</span>
              </div>
              <div>
                <strong>{formatNumber(data.breadth.declines, 0)}</strong>
                <span>Declines</span>
              </div>
              <div>
                <strong>{formatNumber(data.breadth.unchanged, 0)}</strong>
                <span>Unchanged</span>
              </div>
              <div>
                <strong>{data.breadth.ratio.toFixed(2)}x</strong>
                <span>A/D Ratio</span>
              </div>
            </div>

            <div className="breadth-bar">
              <div style={{ width: `${breadthPercent}%` }} />
            </div>
            <div className="bar-labels">
              <span>ADVANCES {breadthPercent.toFixed(0)}%</span>
              <span>DECLINES {(100 - breadthPercent).toFixed(0)}%</span>
            </div>
          </article>

          <article className="watch-card">
            <div className="metric-title">NIFTY WATCH</div>
            <div className="index-row">
              <div>
                <strong>NIFTY 50</strong>
                <span>{formatNumber(data.nifty50.value)}</span>
              </div>
              <div className="positive-text">{pct(data.nifty50.change_percent)}</div>
            </div>
            <div className="mini-line"><span style={{ width: "72%" }} /></div>

            <div className="index-row">
              <div>
                <strong>BANK NIFTY</strong>
                <span>{formatNumber(data.bank_nifty.value)}</span>
              </div>
              <div className="positive-text">{pct(data.bank_nifty.change_percent)}</div>
            </div>
            <div className="mini-line"><span style={{ width: "81%" }} /></div>
          </article>
        </section>

        <div className="section-heading">
          <div>
            <span className="section-kicker">04 / SIGNAL ENGINE</span>
            <h2>Why the model is leaning {data.overall_signal.toLowerCase()}</h2>
          </div>
        </div>

        <section className="factor-grid">
          {data.factors.map((factor) => (
            <article className="factor-card" key={factor.label}>
              <div className="factor-status">
                <SignalDot signal={factor.signal} />
                {factor.signal === "positive" ? "POSITIVE" : "NEGATIVE"}
              </div>
              <strong>{factor.label}</strong>
              <span>{factor.value}</span>
              <small>{factor.detail}</small>
            </article>
          ))}
        </section>

        <div className="section-heading">
          <div>
            <span className="section-kicker">05 / HISTORICAL SIGNALS</span>
            <h2>Model timeline</h2>
          </div>
          <span className="data-status live"><span className="status-dot" /> POSTGRESQL</span>
        </div>

        <section className="history-panel">
          {history.length === 0 ? (
            <div className="empty-state">The first persisted signal will appear after the next market refresh.</div>
          ) : history.map((item) => (
            <div className="history-row" key={`${item.timestamp}-${item.score}`}>
              <span className={`signal-dot ${item.signal === "BULLISH" ? "positive" : item.signal === "BEARISH" ? "negative" : "neutral"}`} />
              <time>{new Date(item.timestamp).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</time>
              <strong>{item.signal}</strong>
              <span>{item.score}/100</span>
              <small>{item.confidence} confidence</small>
            </div>
          ))}
        </section>

        <div className="section-heading">
          <div>
            <span className="section-kicker">06 / DERIVATIVES</span>
            <h2>Options positioning & conviction</h2>
          </div>
          {derivatives && <span className={`data-status ${derivatives.freshness === "live" ? "live" : "stale"}`}><span className="status-dot" /> {derivatives.freshness.toUpperCase()}</span>}
        </div>

        <section className="derivatives-layout">
          <article className="derivatives-card">
            <div className="metric-title">{derivatives?.symbol || "NIFTY"} OPTIONS</div>
            {derivatives?.freshness === "live" ? (
              <>
                <div className="derivatives-grid">
                  <div><span>PCR</span><strong>{derivatives.pcr?.toFixed(2) ?? "-"}</strong></div>
                  <div><span>ATM IV</span><strong>{derivatives.atm_iv?.call?.toFixed(2) ?? "-"}%</strong></div>
                  <div><span>MAX PAIN</span><strong>{derivatives.max_pain?.toLocaleString("en-IN") ?? "-"}</strong></div>
                  <div><span>SUPPORT</span><strong>{derivatives.support?.toLocaleString("en-IN") ?? "-"}</strong></div>
                  <div><span>RESISTANCE</span><strong>{derivatives.resistance?.toLocaleString("en-IN") ?? "-"}</strong></div>
                </div>
                <div className="oi-line">Call OI {derivatives.totals?.call_oi.toLocaleString("en-IN")} · Put OI {derivatives.totals?.put_oi.toLocaleString("en-IN")} · ΔOI {derivatives.totals?.call_change_oi.toLocaleString("en-IN")} / {derivatives.totals?.put_change_oi.toLocaleString("en-IN")}</div>
              </>
            ) : <div className="empty-state">Options chain unavailable: {derivatives?.error || "No source response"}</div>}
          </article>
          <article className="recommendation-card">
            <div className="recommendation-heading">
              <div>
                <div className="metric-title">MARKETPULSE CONVICTION DESK</div>
                <div className="recommendation-instrument">{recommendation?.symbol || "NIFTY"} · {recommendation?.leading_sector || "Market view"}</div>
              </div>
              <span className="data-status stale">{recommendation?.data_quality?.status || "PROVISIONAL"}</span>
            </div>
            <div className="recommendation-summary">
              <div>
                <span className="recommendation-label">Overall conviction</span>
                <strong className={`recommendation-bias ${recommendation?.bias.toLowerCase()}`}>{recommendation?.overall_score ?? "-"}<small>/100</small></strong>
                <span className="recommendation-classification">{(recommendation?.classification || recommendation?.bias || "UNAVAILABLE").replaceAll("_", " ")}</span>
              </div>
              <div className="recommendation-scores">
                <div><span>Investment</span><strong>{recommendation?.investment_score ?? "-"}</strong></div>
                <div><span>Trading</span><strong>{recommendation?.trading_score ?? "-"}</strong></div>
                <div><span>Options</span><strong>{recommendation?.derivatives_signal ?? "-"}</strong></div>
              </div>
            </div>
            <div className="recommendation-factors">
              {Object.entries(recommendationScoreLabels).map(([key, label]) => {
                const score = recommendation?.scores?.[key]
                return <div className="factor-meter" key={key}><div><span>{label}</span><strong>{score ?? "Pending"}</strong></div><i><em style={{ width: `${score ?? 0}%` }} /></i></div>
              })}
            </div>
            <div className="recommendation-columns">
              <div><span className="recommendation-label">Why it qualifies</span>{(recommendation?.thesis || ["Awaiting the next collector cycle."]).map((item) => <p key={item}>{item}</p>)}</div>
              <div><span className="recommendation-label">Risk flags</span>{(recommendation?.risks || ["Risk assessment pending."]).map((item) => <p key={item}>{item}</p>)}</div>
            </div>
            {recommendation?.setups.map((setup) => <div className="setup-row" key={setup.direction}><strong>{setup.direction}</strong><span>{setup.trigger} · Risk {setup.risk}</span><small>{setup.reason}</small></div>)}
            <small className="recommendation-disclaimer">{recommendation?.disclaimer}</small>
          </article>
        </section>

        <div className="method-note">
          <strong>Data status:</strong> quotes are collected from external market
          sources. A stale label means at least one source failed or has no configured
          live feed; verify timestamps before acting on the dashboard.
        </div>
      </main>

      <footer>
        <span>MARKETPULSE INDIA · v0.4</span>
        <span>Analysis only · Not financial advice</span>
      </footer>
    </div>
  )
}

export default App

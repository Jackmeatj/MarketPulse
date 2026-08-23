# MarketPulse India

Indian stock market analysis and derivatives platform.

## Technology

- React
- TypeScript
- FastAPI
- Python
- PostgreSQL
- Redis
- Docker

## Development

The application is designed to run locally using Docker Compose.

## Indian sector data sources

For sector breadth and performance, the preferred source is NSE India's official
sectoral-index feed. Its `allIndices` response includes indices such as NIFTY Auto,
Bank, Financial Services, FMCG, Healthcare, IT, Media, Metal, Pharma, Private Bank,
PSU Bank, Realty and Oil & Gas. Use the index value, change, percentage change and
timestamp from that feed rather than scraping a chart page.

BSE India's official sector and industry indices are a useful cross-check for BSE-listed
coverage. For a production system, a licensed vendor such as Bloomberg, LSEG, FactSet,
or an exchange-authorized market-data vendor is preferable when guaranteed uptime,
entitlements and redistribution rights are required. Yahoo Finance is useful for broad
index context, but should not be treated as the authoritative NSE sector feed.

The next sector endpoint should return each index with `value`, `change_percent`,
`timestamp`, `source`, `freshness`, and a market-session state, matching the existing
global-market contract.

The current sector endpoint is `GET /api/sectors`. It returns the 20-sector core
universe, NIFTY-relative 1D strength, score/classification, rotation buckets, and
NSE availability. Historical EMA/RSI/ROC, constituent breadth, velocity, ATR and
NSE/BSE confirmation are intentionally marked as the next ingestion phase because
they require historical candles and constituent-level feeds.
# MarketPulse v0.4 — Historical Storage and Derivatives

This stage replaces the dashboard demo values with source-aware market collectors.
It also adds Redis as the latest-data buffer, PostgreSQL signal history, NSE options-chain
analytics, and a transparent rule-based recommendation output.

## Run

From the project root:

```bash
docker compose up -d --build
```

Open:

- Frontend: http://localhost:5173
- API: http://localhost:8000
- API docs: http://localhost:8000/docs

## Current data status

The dashboard reads source-tagged values returned by:

`GET /api/market/overview`

Yahoo Finance supplies Nasdaq, Dow Jones, India VIX, NIFTY 50 and BANK NIFTY quotes.
NSE India's public indices feed supplies market breadth. Each value includes a source,
timestamp and `live`, `stale` or `unavailable` freshness state.

GIFT NIFTY requires a configured upstream symbol because no verified public symbol is
available in the default feeds. Set `GIFT_NIFTY_YAHOO_SYMBOL` only after verifying the
symbol with the provider; the dashboard will show it as unavailable rather than use a
proxy value when it is not configured.

## v0.4 endpoints

- `GET /api/market/history` — persisted signal timeline
- `GET /api/derivatives/options?symbol=NIFTY` — OI, change in OI, PCR, IV, max pain, support/resistance
- `GET /api/recommendation?symbol=NIFTY` — market and derivatives bias with conditional setups
- `GET /health/storage` — Redis and PostgreSQL readiness

The default NSE options endpoint currently returns `404` in this environment. The
collector reports that source as unavailable and accepts `OPTIONS_CHAIN_URL` for a
verified provider or licensed feed.

## Current panels

- Overall market opening bias and score
- Nasdaq
- Dow Jones
- GIFT NIFTY
- India VIX
- NSE advances/declines
- Advance/decline ratio
- NIFTY 50
- BANK NIFTY
- Signal-engine explanation

## Important

External feeds can be delayed, unavailable or subject to provider terms and rate limits.
The API preserves the last successful quote in process memory and marks it stale after a
subsequent collection failure. This is not yet historical storage or an execution feed.

The project's requested India VIX rule is implemented literally for now:

- VIX > 15 -> positive
- VIX <= 15 -> negative

This is a project-specific heuristic and should be reviewed before using the system for actual trading decisions.

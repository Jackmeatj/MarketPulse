# Dhan Token Manager

Fully automated daily access-token generation for Dhan's API, using the
PIN + TOTP flow (no browser, no manual login after one-time setup).

## Files

- `token_manager.py` — core logic: `get_valid_token()` returns a cached
  or freshly-generated token, with retry/backoff and expiry handling.
- `test_token_manager.py` — mocked unit tests, no real credentials needed.
  Run with: `python -m pytest test_token_manager.py -v`
- `check_live_connection.py` — one-time real-credential check against
  Dhan's actual API (read-only, doesn't touch orders/positions).

## One-time setup (~5 minutes)

1. **Get your API Key & Secret** (valid 12 months):
   Log in to `web.dhan.co` → Profile → "Access DhanHQ APIs" → API Key tab.
   (Not strictly needed for the PIN+TOTP flow used here, but keep them —
   you'll want them if you later add the trading/order APIs.)

2. **Get your TOTP secret** — this is the *setup key* Dhan shows you
   when you first enable 2FA/authenticator app login (usually shown as
   text or a QR code you scan into Google Authenticator). If you already
   have 2FA enabled and don't have the original secret saved, you'll need
   to reset/re-enable 2FA on Dhan to get a fresh one — this is the only
   piece that requires a manual dashboard step, and it's one-time.

3. **Set environment variables** (don't hardcode these anywhere):
   ```bash
   export DHAN_CLIENT_ID="your_client_id"
   export DHAN_PIN="your_pin"
   export DHAN_TOTP_SECRET="your_totp_base32_secret"
   ```
   For production, put these in a proper secrets manager or a
   `chmod 600` env file loaded at startup — not your shell history.

4. **Test with mocks first** (safe, no real API calls):
   ```bash
   python -m pytest test_token_manager.py -v
   ```

5. **Test against the real API**:
   ```bash
   python check_live_connection.py
   ```
   You should see `[OK] Token verified against live API.`

## Daily automation

Schedule `token_manager.py` to run once each morning before market open,
e.g. via cron:
```
0 8 * * 1-5 cd /path/to/dhan_pipeline && /usr/bin/python3 token_manager.py >> logs/token.log 2>&1
```
It's idempotent — if the cached token is still valid it does nothing,
so running it more often than needed is harmless.

Any other script in your pipeline should call:
```python
from token_manager import get_valid_token
access_token, client_id = get_valid_token()
```
instead of managing tokens itself.

## Notes

- Dhan's **Data API** (live quotes / historical data, as opposed to the
  free order/trading API) is a separate ₹499/month subscription,
  auto-debited from your trading ledger. Auth is the same either way.
- The cached token lives in `.dhan_token_cache.json` in this folder —
  it's a live credential, treat it like a password (it's created with
  `chmod 600` automatically, but don't commit it to git).

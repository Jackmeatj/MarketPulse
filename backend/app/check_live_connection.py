"""
Run this AFTER setting real env vars to confirm the token manager
works against Dhan's actual API — not just mocks.

Usage:
    export DHAN_CLIENT_ID="your_client_id"
    export DHAN_PIN="your_pin"
    export DHAN_TOTP_SECRET="your_totp_base32_secret"
    python check_live_connection.py

What it does:
    1. Generates (or reuses cached) access token via token_manager.
    2. Calls a lightweight, harmless read-only endpoint (user profile)
       to confirm the token actually authenticates.
    3. Prints clear pass/fail — does NOT place any orders or touch
       your positions/holdings.
"""

from dhanhq import DhanLogin
from token_manager import get_valid_token, DhanAuthError


def main():
    try:
        access_token, client_id = get_valid_token()
    except DhanAuthError as e:
        print(f"[FAIL] Could not obtain token: {e}")
        return

    print(f"[OK] Got access token for client {client_id} "
          f"(first 12 chars: {access_token[:12]}...)")

    try:
        dhan_login = DhanLogin(client_id)
        profile = dhan_login.user_profile(access_token)
        print(f"[OK] Token verified against live API. Profile response: {profile}")
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] Token generated but verification call failed: {e}")


if __name__ == "__main__":
    main()

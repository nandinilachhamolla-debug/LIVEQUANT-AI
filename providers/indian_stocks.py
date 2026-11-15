"""
Indian stock market (NSE/BSE) provider status for LIVEQUANT AI.

This module never returns prices. It only reports whether a legitimate,
authorized market-data provider is configured and connected, and explains
exactly what is required when it is not.

Rules enforced here:
  * No scraping, no unofficial endpoints, no authentication bypass.
  * No simulated, hardcoded or placeholder prices.
  * Delayed data must never be reported as LIVE.
  * Credentials come from environment variables only; their values are
    never returned by the API (only SET / NOT_SET).

A real provider adapter (one per broker/vendor) will be added once the
provider and credentials are chosen. Until then the status is always
NOT_CONNECTED.
"""

import logging
import os

logger = logging.getLogger("livequant.stocks")

ENV_PROVIDER = "INDIAN_STOCK_PROVIDER"
ENV_API_KEY = "INDIAN_STOCK_API_KEY"
ENV_ACCESS_TOKEN = "INDIAN_STOCK_ACCESS_TOKEN"

# Candidate authorized providers. Requirements are summaries; always confirm
# current pricing, terms and authentication flow on the provider's developer
# portal before relying on them.
KNOWN_PROVIDERS = {
    "upstox": {
        "display_name": "Upstox API",
        "requirements": [
            "Upstox trading account with an API app (API key and secret)",
            "Login/OAuth flow to obtain an access token (tokens expire daily)",
        ],
    },
    "angelone": {
        "display_name": "Angel One SmartAPI",
        "requirements": [
            "Angel One account with a SmartAPI app (API key)",
            "Client code, PIN and TOTP for session login",
        ],
    },
    "kite": {
        "display_name": "Zerodha Kite Connect",
        "requirements": [
            "Zerodha account and a Kite Connect app (API key and secret)",
            "Paid Kite Connect subscription for market data",
            "Daily login flow to obtain an access token",
        ],
    },
    "dhan": {
        "display_name": "Dhan API",
        "requirements": [
            "Dhan account with API access (client id and access token)",
            "Check whether live market-data access requires an extra plan",
        ],
    },
    "fyers": {
        "display_name": "Fyers API",
        "requirements": [
            "Fyers account with an API app (app id and secret)",
            "Daily auth flow to obtain an access token",
        ],
    },
}

# Adapters that are actually implemented and tested. Empty for now.
IMPLEMENTED_ADAPTERS = set()


def _env_flag(name: str) -> str:
    return "SET" if os.getenv(name, "").strip() else "NOT_SET"


def get_indian_stock_provider_status() -> dict:
    """Return the current NSE/BSE connectivity status. Never returns prices."""
    provider_key = os.getenv(ENV_PROVIDER, "").strip().lower()

    base = {
        "provider": None,
        "status": "NOT_CONNECTED",
        "data_mode": "UNAVAILABLE",
        "supported_symbols": [],
        "reason": "",
        "requirements": [],
        "candidate_providers": {
            key: info["display_name"] for key, info in KNOWN_PROVIDERS.items()
        },
        "environment": {
            ENV_PROVIDER: _env_flag(ENV_PROVIDER),
            ENV_API_KEY: _env_flag(ENV_API_KEY),
            ENV_ACCESS_TOKEN: _env_flag(ENV_ACCESS_TOKEN),
        },
    }

    if not provider_key:
        base["reason"] = (
            "No NSE/BSE market-data provider is configured. "
            "No stock prices are served."
        )
        base["requirements"] = [
            f"Choose an authorized provider and set {ENV_PROVIDER} "
            f"to one of: {', '.join(KNOWN_PROVIDERS)}",
            f"Set {ENV_API_KEY} and {ENV_ACCESS_TOKEN} in your .env file",
            "Restart the backend after editing .env",
        ]
        return base

    if provider_key not in KNOWN_PROVIDERS:
        base["reason"] = (
            f"Unknown provider '{provider_key}'. "
            f"Supported choices: {', '.join(KNOWN_PROVIDERS)}."
        )
        base["requirements"] = [
            f"Set {ENV_PROVIDER} to one of: {', '.join(KNOWN_PROVIDERS)}"
        ]
        return base

    info = KNOWN_PROVIDERS[provider_key]
    base["provider"] = info["display_name"]
    base["requirements"] = list(info["requirements"])

    if provider_key not in IMPLEMENTED_ADAPTERS:
        base["reason"] = (
            f"{info['display_name']} is selected, but its adapter is not "
            "implemented in this build yet. No stock prices are served."
        )
        logger.info("Stock provider '%s' selected but adapter not implemented",
                    provider_key)
        return base

    # Reserved for future adapters: a connected adapter would report its own
    # status, data_mode (LIVE or DELAYED) and supported symbols here.
    base["reason"] = "Adapter reported no status."
    return base
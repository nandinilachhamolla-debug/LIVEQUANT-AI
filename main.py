
from services.analytics import calculate_analytics
import asyncio
import logging
import os
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from providers.indian_stocks import get_indian_stock_provider_status
from routers.equity import router as equity_router

# Load credentials/config from a local .env file.
load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)
logger = logging.getLogger("livequant")

# --------------------------------------------------
# LIVEQUANT AI - BACKEND CONFIGURATION
# --------------------------------------------------

COINDCX_TICKER_URL = "https://api.coindcx.com/exchange/ticker"
POLL_SECONDS = float(os.getenv("CRYPTO_POLL_SECONDS", "5"))
CRYPTO_PREFERRED_SYMBOL = "BTCUSDT"

LIVE_MAX_AGE_SECONDS = float(
    os.getenv("LIVE_MAX_AGE_SECONDS", str(max(POLL_SECONDS * 3, 20)))
)
UNAVAILABLE_AFTER_SECONDS = float(
    os.getenv("DATA_UNAVAILABLE_AFTER_SECONDS", "300")
)

market_data = {
    "crypto": deque(maxlen=500),
    "stocks": deque(maxlen=500)
}

connections = set()

market_status = {
    "crypto": "CONNECTING",
    "stocks": "NOT_CONNECTED"
}

market_health = {
    "crypto": {
        "last_success": None,
        "last_error": None,
        "last_error_at": None,
        "consecutive_failures": 0
    },
    "stocks": {
        "last_success": None,
        "last_error": None,
        "last_error_at": None,
        "consecutive_failures": 0
    }
}


# --------------------------------------------------
# DATA FRESHNESS HELPERS
# --------------------------------------------------

def iso_or_none(value):
    return value.isoformat() if value else None


def get_data_mode(market: str) -> dict:
    last = market_health[market]["last_success"]

    if last is None:
        return {
            "data_mode": "UNAVAILABLE",
            "data_age_seconds": None
        }

    age = (datetime.now(timezone.utc) - last).total_seconds()

    if age <= LIVE_MAX_AGE_SECONDS:
        mode = "LIVE"
    elif age <= UNAVAILABLE_AFTER_SECONDS:
        mode = "DELAYED"
    else:
        mode = "UNAVAILABLE"

    return {
        "data_mode": mode,
        "data_age_seconds": round(age, 1)
    }


def sync_stock_status() -> dict:
    provider_status = get_indian_stock_provider_status()
    market_status["stocks"] = provider_status["status"]
    return provider_status


# --------------------------------------------------
# WEBSOCKET BROADCAST
# --------------------------------------------------

async def broadcast(data):
    disconnected = []

    for connection in connections:
        try:
            await connection.send_json(data)
        except Exception:
            disconnected.append(connection)

    for connection in disconnected:
        connections.discard(connection)


# --------------------------------------------------
# CRYPTOCURRENCY DATA CONNECTOR
# --------------------------------------------------

async def fetch_crypto_data(client):
    response = await client.get(
        COINDCX_TICKER_URL,
        timeout=15
    )

    response.raise_for_status()
    rows = response.json()

    if not isinstance(rows, list):
        raise ValueError("Unexpected ticker response")

    matches = [
        row for row in rows
        if isinstance(row, dict)
        and "BTC" in str(row.get("market", "")).upper()
        and "USDT" in str(row.get("market", "")).upper()
    ]

    if not matches:
        raise ValueError("BTC/USDT market not found in ticker response")

    exact = [
        row for row in matches
        if str(row.get("market", "")).upper() == CRYPTO_PREFERRED_SYMBOL
    ]

    row = exact[0] if exact else matches[0]

    price = float(row["last_price"])
    volume = float(row["volume"])
    bid = float(row["bid"])
    ask = float(row["ask"])

    if price <= 0 or bid < 0 or ask < 0:
        raise ValueError("Invalid market observation")

    return {
        "market": "crypto",
        "provider": "CoinDCX",
        "symbol": row["market"],
        "price": price,
        "volume_24h": volume,
        "bid": bid,
        "ask": ask,
        "spread": ask - bid,
        "provider_timestamp": row.get("timestamp"),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "data_type": "LIVE_PROVIDER_OBSERVATION"
    }


async def crypto_data_worker():
    health = market_health["crypto"]

    async with httpx.AsyncClient() as client:
        while True:
            try:
                observation = await fetch_crypto_data(client)

                market_data["crypto"].append(observation)
                market_status["crypto"] = "CONNECTED"

                health["last_success"] = datetime.now(timezone.utc)
                health["consecutive_failures"] = 0

                await broadcast({
                    "type": "market_update",
                    "data": observation
                })

                logger.info(
                    "[CRYPTO] %s %s",
                    observation["symbol"],
                    observation["price"]
                )

            except asyncio.CancelledError:
                raise

            except Exception as error:
                market_status["crypto"] = "ERROR"

                health["last_error"] = (
                    f"{type(error).__name__}: {error}"
                )
                health["last_error_at"] = datetime.now(timezone.utc)
                health["consecutive_failures"] += 1

                logger.warning(
                    "[CRYPTO ERROR] %s (consecutive failures: %d)",
                    health["last_error"],
                    health["consecutive_failures"]
                )

                await broadcast({
                    "type": "connection_status",
                    "market": "crypto",
                    "status": "ERROR",
                    "message": str(error)
                })

            await asyncio.sleep(POLL_SECONDS)


# --------------------------------------------------
# APPLICATION LIFECYCLE
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    stock_status = sync_stock_status()

    task = asyncio.create_task(crypto_data_worker())

    logger.info("LIVEQUANT AI backend started")
    logger.info(
        "Indian stocks: %s (%s)",
        stock_status["status"],
        stock_status["reason"]
    )

    yield

    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass


# --------------------------------------------------
# FASTAPI APPLICATION
# --------------------------------------------------

app = FastAPI(
    title="LIVEQUANT AI",
    description="Real-time market intelligence and anomaly monitoring",
    version="1.0.0",
    lifespan=lifespan
)

# Register the Indian stock market API.
app.include_router(equity_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5176",
        "http://127.0.0.1:5176",
        "http://localhost:5175",
        "http://127.0.0.1:5175"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# --------------------------------------------------
# REST API ENDPOINTS
# --------------------------------------------------

@app.get("/")
async def home():
    return {
        "project": "LIVEQUANT AI",
        "message": "Market intelligence backend is running",
        "status": "OK"
    }


@app.get("/api/health")
async def health():
    sync_stock_status()

    return {
        "application": "LIVEQUANT AI",
        "crypto_status": market_status["crypto"],
        "stock_status": market_status["stocks"],
        "crypto_data_mode": get_data_mode("crypto")["data_mode"],
        "stock_data_mode": get_data_mode("stocks")["data_mode"],
        "crypto_observations": len(market_data["crypto"]),
        "stock_observations": len(market_data["stocks"]),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/markets")
async def markets():
    stock_provider = sync_stock_status()

    crypto_health = market_health["crypto"]
    crypto_mode = get_data_mode("crypto")

    if market_data["crypto"]:
        crypto_symbols = [market_data["crypto"][-1]["symbol"]]
    else:
        crypto_symbols = [CRYPTO_PREFERRED_SYMBOL]

    crypto_entry = {
        "id": "crypto",
        "name": "Cryptocurrency",
        "provider": "CoinDCX",
        "status": market_status["crypto"],
        "data_mode": crypto_mode["data_mode"],
        "data_age_seconds": crypto_mode["data_age_seconds"],
        "update_method": "REST_POLLING",
        "poll_interval_seconds": POLL_SECONDS,
        "supported_symbols": crypto_symbols,
        "last_successful_update": iso_or_none(
            crypto_health["last_success"]
        ),
        "observations_buffered": len(market_data["crypto"]),
        "consecutive_failures": crypto_health["consecutive_failures"],
        "last_error": crypto_health["last_error"],
        "last_error_at": iso_or_none(crypto_health["last_error_at"]),
        "note": (
            "Observations are polled from the public CoinDCX REST ticker "
            "at the interval above; this is not an exchange-pushed "
            "tick stream."
        )
    }

    stock_entry = {
        "id": "stocks",
        "name": "Indian Stocks (NSE/BSE)",
        "exchanges": ["NSE", "BSE"],
        "provider": stock_provider["provider"],
        "status": stock_provider["status"],
        "data_mode": stock_provider["data_mode"],
        "data_age_seconds": None,
        "supported_symbols": stock_provider["supported_symbols"],
        "last_successful_update": iso_or_none(
            market_health["stocks"]["last_success"]
        ),
        "observations_buffered": len(market_data["stocks"]),
        "reason": stock_provider["reason"],
        "requirements": stock_provider["requirements"],
        "candidate_providers": stock_provider["candidate_providers"],
        "environment": stock_provider["environment"]
    }

    return {
        "crypto": market_status["crypto"],
        "indian_stocks": market_status["stocks"],
        "supported_markets": [
            "Cryptocurrency",
            "NSE",
            "BSE"
        ],
        "markets": [crypto_entry, stock_entry],
        "generated_at": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/ticks/{market}")
async def get_ticks(market: str, limit: int = 50):
    if market not in market_data:
        return {"error": "Unsupported market"}

    limit = max(1, min(limit, 500))

    return {
        "market": market,
        "count": min(limit, len(market_data[market])),
        "observations": list(market_data[market])[-limit:]
    }


@app.get("/api/latest/{market}")
async def latest(market: str):
    if market not in market_data:
        return {"error": "Unsupported market"}

    if not market_data[market]:
        return {
            "market": market,
            "status": market_status[market],
            "observation": None
        }

    return {
        "market": market,
        "status": market_status[market],
        "observation": market_data[market][-1]
    }


# --------------------------------------------------
# LIVE FRONTEND WEBSOCKET
# --------------------------------------------------

@app.websocket("/ws/market")
async def market_websocket(websocket: WebSocket):
    await websocket.accept()
    connections.add(websocket)

    try:
        await websocket.send_json({
            "type": "connection_status",
            "market": "all",
            "status": "CONNECTED"
        })

        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        connections.discard(websocket)

    except Exception:
        connections.discard(websocket)


# --------------------------------------------------
# MATHEMATICAL ANALYTICS API
# --------------------------------------------------

@app.get("/api/analytics/{market}")
async def market_analytics(market: str):
    if market not in market_data:
        return {
            "error": "Unsupported market",
            "supported": ["crypto", "stocks"]
        }

    observations = list(market_data[market])
    result = calculate_analytics(observations)

    return {
        "project": "LIVEQUANT AI",
        "market": market,
        "provider_status": market_status[market],
        "analysis": result,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/alerts/{market}")
async def market_alerts(market: str):
    if market not in market_data:
        return {"error": "Unsupported market"}

    result = calculate_analytics(
        list(market_data[market])
    )

    if result.get("status") != "ANALYSIS_COMPLETE":
        return {
            "market": market,
            "status": result.get("status"),
            "alerts": []
        }

    alert_type = result["alert"]

    return {
        "market": market,
        "status": "READY",
        "alerts": [
            {
                "type": alert_type,
                "explanation": result["explanation"],
                "z_score": result[
                    "statistical_analysis"
                ]["z_score"],
                "ml_anomaly": result[
                    "machine_learning"
                ]["anomaly_detected"]
            }
        ]
    }

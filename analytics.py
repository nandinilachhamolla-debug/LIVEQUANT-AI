
import math

import numpy as np
import pandas as pd

from sklearn.ensemble import IsolationForest


def safe_float(value):
    """Convert a numeric value safely."""
    try:
        result = float(value)
        if math.isfinite(result):
            return result
    except (TypeError, ValueError):
        pass

    return None


def calculate_analytics(observations):
    """
    Analyse genuine provider observations.

    Returns insufficient-data status until enough
    distinct observations are available.
    """

    if len(observations) < 3:
        return {
            "status": "INSUFFICIENT_DATA",
            "message": "Collecting market observations.",
            "observations_available": len(observations),
            "minimum_required": 20
        }

    df = pd.DataFrame(list(observations))

    required = ["price", "bid", "ask", "volume_24h"]

    if not all(column in df.columns for column in required):
        return {
            "status": "INVALID_DATA",
            "message": "Required market fields are missing."
        }

    for column in required:
        df[column] = pd.to_numeric(
            df[column], errors="coerce"
        )

    df = df.dropna(subset=required)

    df = df[
        (df["price"] > 0) &
        (df["bid"] >= 0) &
        (df["ask"] >= 0) &
        (df["volume_24h"] >= 0)
    ]

    # Do not treat repeated identical observations
    # as independent market movements.
    df = df.drop_duplicates(
        subset=["received_at"],
        keep="last"
    )

    df = df.reset_index(drop=True)

    if len(df) < 3:
        return {
            "status": "INSUFFICIENT_DATA",
            "message": "Not enough valid observations.",
            "observations_available": len(df),
            "minimum_required": 20
        }

    # ------------------------------------------------
    # 1. PRICE RETURNS
    # ------------------------------------------------

    df["return_pct"] = (
        df["price"].pct_change() * 100
    )

    # ------------------------------------------------
    # 2. ORDER BOOK SPREAD
    # ------------------------------------------------

    df["mid_price"] = (
        df["bid"] + df["ask"]
    ) / 2

    df["spread_pct"] = np.where(
        df["mid_price"] > 0,
        (df["ask"] - df["bid"])
        / df["mid_price"] * 100,
        np.nan
    )

    # ------------------------------------------------
    # 3. VOLUME TRANSFORMATION
    # ------------------------------------------------

    df["log_volume"] = np.log1p(
        df["volume_24h"]
    )

    # Remove first row because percentage return
    # cannot be calculated without a previous price.
    features = df[
        ["return_pct", "spread_pct", "log_volume"]
    ].replace([np.inf, -np.inf], np.nan).dropna()

    if len(features) < 20:
        return {
            "status": "INSUFFICIENT_DATA",
            "message": "Waiting for 20 valid observations.",
            "observations_available": len(features),
            "minimum_required": 20
        }

    # ------------------------------------------------
    # 4. VOLATILITY
    # ------------------------------------------------

    returns = features["return_pct"]

    volatility = float(
        returns.std(ddof=1)
    )

    average_return = float(
        returns.mean()
    )

    # ------------------------------------------------
    # 5. Z-SCORE
    # ------------------------------------------------

    return_std = float(returns.std(ddof=1))

    if return_std > 1e-12:
        z_score = float(
            (returns.iloc[-1] - average_return)
            / return_std
        )
    else:
        z_score = 0.0

    statistical_anomaly = abs(z_score) >= 3

    # ------------------------------------------------
    # 6. ISOLATION FOREST
    # ------------------------------------------------

    model = IsolationForest(
        n_estimators=100,
        contamination="auto",
        random_state=42
    )

    model.fit(features)

    prediction = int(
        model.predict(features.tail(1))[0]
    )

    anomaly_score = float(
        model.decision_function(
            features.tail(1)
        )[0]
    )

    ml_anomaly = prediction == -1

    # ------------------------------------------------
    # 7. LIQUIDITY INDICATORS
    # ------------------------------------------------

    latest = df.iloc[-1]

    latest_price = float(latest["price"])
    latest_bid = float(latest["bid"])
    latest_ask = float(latest["ask"])

    spread_pct = safe_float(
        latest["spread_pct"]
    )

    # ------------------------------------------------
    # 8. ALERT CLASSIFICATION
    # ------------------------------------------------

    if statistical_anomaly or ml_anomaly:
        alert = "UNUSUAL_ACTIVITY"
    else:
        alert = "NORMAL_PATTERN"

    return {
        "status": "ANALYSIS_COMPLETE",
        "observations_available": len(features),

        "price_analysis": {
            "latest_price": latest_price,
            "latest_return_pct": safe_float(
                latest["return_pct"]
            ),
            "average_return_pct": average_return
        },

        "volatility": {
            "return_standard_deviation_pct": volatility
        },

        "statistical_analysis": {
            "z_score": z_score,
            "anomaly_detected": statistical_anomaly
        },

        "machine_learning": {
            "algorithm": "Isolation Forest",
            "anomaly_detected": ml_anomaly,
            "decision_score": anomaly_score
        },

        "liquidity_analysis": {
            "best_bid": latest_bid,
            "best_ask": latest_ask,
            "spread": latest_ask - latest_bid,
            "spread_pct": spread_pct,
            "status": (
                "VALID_SPREAD"
                if latest_ask >= latest_bid and latest_bid > 0
                else "INVALID_OR_UNAVAILABLE"
            )
        },

        "alert": alert,

        "explanation": (
            "Unusual statistical or machine-learning "
            "pattern detected. Review the indicators."
            if alert == "UNUSUAL_ACTIVITY"
            else "No anomaly detected by the current models."
        )
    }

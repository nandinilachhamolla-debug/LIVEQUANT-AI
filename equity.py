from pathlib import Path

import joblib
import pandas as pd
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/equity", tags=["Indian Stocks"])

ROOT = Path(__file__).resolve().parents[1]

DATA_FILE = ROOT / "data" / "processed" / "nse_equity_features_v3.csv"
MODEL_FILE = ROOT / "models" / "equity_random_forest_v1.joblib"

FEATURES = [
    "DailyReturnPct", "SMA_5", "EMA_12",
    "Open", "High", "Low", "Close",
    "Volume", "TradedValue", "TotalTrades"
]

LABELS = {
    0: "DOWN",
    1: "UP",
    2: "SIDEWAYS"
}


def load_data():
    if not DATA_FILE.exists():
        raise HTTPException(503, "NSE dataset not found")

    df = pd.read_csv(DATA_FILE)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Symbol"] = df["Symbol"].astype(str).str.upper()
    return df.dropna(subset=["Date", "Symbol"])


def load_model():
    if not MODEL_FILE.exists():
        raise HTTPException(503, "Trained model not found")

    return joblib.load(MODEL_FILE)


@router.get("/status")
def equity_status():
    return {
        "dataset_available": DATA_FILE.exists(),
        "model_available": MODEL_FILE.exists(),
        "data_type": "HISTORICAL_NSE_EOD",
        "prediction_type": "EXPERIMENTAL_NEXT_SESSION"
    }


@router.get("/symbols")
def equity_symbols():
    df = load_data()
    symbols = sorted(df["Symbol"].unique().tolist())

    return {
        "count": len(symbols),
        "symbols": symbols
    }


@router.get("/history/{symbol}")
def equity_history(symbol: str, limit: int = 60):
    df = load_data()
    symbol = symbol.upper()

    rows = df[df["Symbol"] == symbol].sort_values("Date")

    if rows.empty:
        raise HTTPException(404, "Stock symbol not found")

    rows = rows.tail(max(1, min(limit, 250)))

    result = rows[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    result["Date"] = result["Date"].dt.strftime("%Y-%m-%d")

    return {
        "symbol": symbol,
        "count": len(result),
        "history": result.where(pd.notna(result), None).to_dict("records")
    }


@router.get("/predict/{symbol}")
def equity_predict(symbol: str):
    df = load_data()
    symbol = symbol.upper()

    rows = df[df["Symbol"] == symbol].sort_values("Date")

    if rows.empty:
        raise HTTPException(404, "Stock symbol not found")

    latest = rows.iloc[-1]

    model = load_model()
    X = pd.DataFrame(
        [[latest.get(feature) for feature in FEATURES]],
        columns=FEATURES
    )

    prediction = int(model.predict(X)[0])
    scores = model.predict_proba(X)[0]
    classes = model.classes_

    score_map = {
        LABELS[int(class_id)]: round(float(score) * 100, 2)
        for class_id, score in zip(classes, scores)
    }

    return {
        "symbol": symbol,
        "prediction": LABELS.get(prediction, "UNKNOWN"),
        "model_scores_percent": score_map,
        "latest_close": float(latest["Close"]),
        "latest_session": latest["Date"].strftime("%Y-%m-%d"),
        "data_type": "HISTORICAL_NSE_EOD",
        "model": "Random Forest",
        "warning": "Experimental model; scores are not calibrated probabilities or trading advice."
    }
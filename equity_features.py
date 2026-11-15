from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = ROOT / "data" / "processed" / "nse_equity_history.csv"
OUTPUT_DIR = ROOT / "data" / "processed"

REQUIRED_COLUMNS = [
    "Date", "Symbol", "Open", "High", "Low",
    "Close", "Volume"
]


def calculate_rsi(series, period=14):
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    return rsi


def build_features(df):
    frames = []

    for symbol, group in df.groupby("Symbol"):
        group = group.sort_values("Date").copy()

        close = group["Close"]
        volume = group["Volume"]

        # Daily price movement
        group["Daily_Return"] = close.pct_change()

        # Moving averages
        group["SMA_5"] = close.rolling(5, min_periods=5).mean()
        group["SMA_10"] = close.rolling(10, min_periods=10).mean()

        # Exponential moving averages
        group["EMA_5"] = close.ewm(
            span=5, adjust=False, min_periods=5
        ).mean()

        group["EMA_10"] = close.ewm(
            span=10, adjust=False, min_periods=10
        ).mean()

        # RSI
        group["RSI_14"] = calculate_rsi(close, 14)

        # MACD
        ema_12 = close.ewm(
            span=12, adjust=False, min_periods=12
        ).mean()

        ema_26 = close.ewm(
            span=26, adjust=False, min_periods=26
        ).mean()

        group["MACD"] = ema_12 - ema_26

        group["MACD_Signal"] = group["MACD"].ewm(
            span=9, adjust=False, min_periods=9
        ).mean()

        group["MACD_Histogram"] = (
            group["MACD"] - group["MACD_Signal"]
        )

        # Rolling volatility (20 sessions)
        group["Volatility_20"] = (
            group["Daily_Return"]
            .rolling(20, min_periods=20)
            .std()
        )

        # Volume change
        group["Volume_Change"] = volume.pct_change()

        # Future return label: 1 = next session positive,
        # 0 = next session non-positive.
        group["Next_Day_Return"] = close.shift(-1) / close - 1

        group["Target"] = np.where(
            group["Next_Day_Return"].notna(),
            (group["Next_Day_Return"] > 0).astype(int),
            np.nan
        )

        frames.append(group)

    return pd.concat(frames, ignore_index=True)


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Historical dataset not found: {INPUT_FILE}"
        )

    df = pd.read_csv(INPUT_FILE)

    missing = set(REQUIRED_COLUMNS) - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    numeric_columns = [
        "Open", "High", "Low", "Close", "Volume"
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column], errors="coerce"
        )

    df = df.dropna(
        subset=["Date", "Symbol", "Close", "Volume"]
    )

    df = df[df["Close"] > 0]
    df = df[df["Volume"] >= 0]

    df = df.sort_values(["Symbol", "Date"])

    features = build_features(df)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_file = OUTPUT_DIR / "nse_equity_features.csv"
    features.to_csv(output_file, index=False)

    print("\n========== EQUITY FEATURE SUMMARY ==========")
    print("Records:", len(features))
    print("Unique symbols:", features["Symbol"].nunique())
    print("Trading sessions:", features["Date"].nunique())
    print("Date range:",
          features["Date"].min().date(),
          "to",
          features["Date"].max().date())

    print("\nFeature columns:")
    print([
        "Daily_Return", "SMA_5", "SMA_10",
        "EMA_5", "EMA_10", "RSI_14",
        "MACD", "MACD_Signal", "MACD_Histogram",
        "Volatility_20", "Volume_Change",
        "Next_Day_Return", "Target"
    ])

    print("\nAvailable RSI values:", features["RSI_14"].notna().sum())
    print("Available SMA_5 values:", features["SMA_5"].notna().sum())
    print("Available target labels:", features["Target"].notna().sum())

    print("\nOutput:", output_file)
    print("\nFeature engineering completed.")


if __name__ == "__main__":
    main()

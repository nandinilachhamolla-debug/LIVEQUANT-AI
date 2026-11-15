
import json
import zipfile
import warnings
from pathlib import Path
from io import BytesIO

import numpy as np
import pandas as pd


# ============================================================
# LIVEQUANT-AI
# NSE EQUITY DATASET BUILDER
# Corrected version: BizDt date handling
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent.parent

RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

HISTORY_OUTPUT = PROCESSED_DIR / "nse_equity_history_v3.csv"
FEATURES_OUTPUT = PROCESSED_DIR / "nse_equity_features_v3.csv"
SUMMARY_OUTPUT = PROCESSED_DIR / "equity_data_summary_v3.json"

# NSE columns
REQUIRED_COLUMNS = [
    "BizDt",
    "TckrSymb",
    "SctySrs",
    "OpnPric",
    "HghPric",
    "LwPric",
    "ClsPric",
    "PrvsClsgPric",
    "TtlTradgVol",
    "TtlTrfVal",
    "TtlNbOfTxsExctd",
]


# ============================================================
# DATE CONVERSION
# ============================================================

def parse_nse_dates(series):

    values = series.astype(str).str.strip()

    # NSE BizDt is normally YYYY-MM-DD.
    dates = pd.to_datetime(
        values,
        format="%Y-%m-%d",
        errors="coerce"
    )

    # Support alternative date formats without interpreting
    # ISO dates using dayfirst=True.
    missing = dates.isna()

    alternative_formats = [
        "%d-%b-%Y",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y%m%d",
    ]

    for date_format in alternative_formats:

        if not missing.any():
            break

        parsed = pd.to_datetime(
            values.loc[missing],
            format=date_format,
            errors="coerce"
        )

        dates.loc[missing] = parsed
        missing = dates.isna()

    return dates


# ============================================================
# READ NSE ZIP FILES
# ============================================================

def read_nse_zip(zip_path):

    frames = []

    try:

        with zipfile.ZipFile(zip_path, "r") as archive:

            csv_files = [
                name for name in archive.namelist()
                if name.lower().endswith(".csv")
            ]

            if not csv_files:
                print(f"WARNING: No CSV found in {zip_path.name}")
                return pd.DataFrame()

            for csv_name in csv_files:

                with archive.open(csv_name) as file:

                    df = pd.read_csv(
                        BytesIO(file.read()),
                        low_memory=False
                    )

                    df.columns = (
                        df.columns.astype(str).str.strip()
                    )

                    missing_columns = [
                        col for col in REQUIRED_COLUMNS
                        if col not in df.columns
                    ]

                    if missing_columns:
                        print(
                            f"WARNING: Skipping {csv_name}. "
                            f"Missing columns: {missing_columns}"
                        )
                        continue

                    # IMPORTANT:
                    # BizDt is the business/trading date.
                    # Do not use TradDt as the canonical date.
                    df = df.rename(
                        columns={
                            "BizDt": "Date",
                            "TckrSymb": "Symbol",
                            "SctySrs": "Series",
                            "OpnPric": "Open",
                            "HghPric": "High",
                            "LwPric": "Low",
                            "ClsPric": "Close",
                            "PrvsClsgPric": "PreviousClose",
                            "TtlTradgVol": "Volume",
                            "TtlTrfVal": "TradedValue",
                            "TtlNbOfTxsExctd": "TotalTrades",
                        }
                    )

                    # Keep normal equity series only.
                    df["Series"] = (
                        df["Series"].astype(str).str.strip()
                    )

                    df = df[df["Series"] == "EQ"].copy()

                    # Correct date parsing.
                    df["Date"] = parse_nse_dates(df["Date"])

                    df["Symbol"] = (
                        df["Symbol"].astype(str).str.strip()
                    )

                    numeric_columns = [
                        "Open",
                        "High",
                        "Low",
                        "Close",
                        "PreviousClose",
                        "Volume",
                        "TradedValue",
                        "TotalTrades",
                    ]

                    for col in numeric_columns:

                        df[col] = pd.to_numeric(
                            df[col],
                            errors="coerce"
                        )

                    df = df.dropna(
                        subset=[
                            "Date",
                            "Symbol",
                            "Open",
                            "High",
                            "Low",
                            "Close",
                        ]
                    )

                    df = df[
                        (df["Open"] > 0)
                        & (df["High"] > 0)
                        & (df["Low"] > 0)
                        & (df["Close"] > 0)
                    ]

                    df = df[
                        (df["High"] >= df["Low"])
                        & (df["High"] >= df["Open"])
                        & (df["High"] >= df["Close"])
                        & (df["Low"] <= df["Open"])
                        & (df["Low"] <= df["Close"])
                    ]

                    if not df.empty:
                        frames.append(df)

    except zipfile.BadZipFile:
        print(f"WARNING: Invalid ZIP file: {zip_path.name}")

    except Exception as exc:
        print(f"ERROR reading {zip_path.name}: {exc}")

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


# ============================================================
# TECHNICAL INDICATORS
# ============================================================

def calculate_rsi(series, period=14):

    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        min_periods=period,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        min_periods=period,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    rsi = 100 - (100 / (1 + rs))

    rsi = rsi.mask(
        (avg_loss == 0) & (avg_gain > 0),
        100
    )

    rsi = rsi.mask(
        (avg_gain == 0) & (avg_loss > 0),
        0
    )

    return rsi


def add_technical_indicators(df):

    df = df.sort_values(
        ["Symbol", "Date"]
    ).copy()

    grouped = df.groupby("Symbol", group_keys=False)

    # Daily percentage return
    df["DailyReturnPct"] = (
        grouped["Close"]
        .pct_change()
        .mul(100)
    )

    # Moving averages
    df["SMA_5"] = grouped["Close"].transform(
        lambda x: x.rolling(5, min_periods=5).mean()
    )

    df["SMA_20"] = grouped["Close"].transform(
        lambda x: x.rolling(20, min_periods=20).mean()
    )

    # Exponential moving averages
    df["EMA_12"] = grouped["Close"].transform(
        lambda x: x.ewm(
            span=12,
            adjust=False,
            min_periods=12
        ).mean()
    )

    df["EMA_26"] = grouped["Close"].transform(
        lambda x: x.ewm(
            span=26,
            adjust=False,
            min_periods=26
        ).mean()
    )

    # RSI
    df["RSI_14"] = grouped["Close"].transform(
        lambda x: calculate_rsi(x, 14)
    )

    # MACD
    df["MACD"] = df["EMA_12"] - df["EMA_26"]

    df["MACD_Signal"] = (
        df.groupby("Symbol")["MACD"]
        .transform(
            lambda x: x.ewm(
                span=9,
                adjust=False,
                min_periods=9
            ).mean()
        )
    )

    df["MACD_Histogram"] = (
        df["MACD"] - df["MACD_Signal"]
    )

    return df


# ============================================================
# NEXT-DAY TARGET
# ============================================================

def add_prediction_targets(df):

    df = df.sort_values(
        ["Symbol", "Date"]
    ).copy()

    grouped = df.groupby("Symbol", group_keys=False)

    # Next trading-session return for each symbol.
    df["NextDayReturnPct"] = (
        grouped["Close"]
        .transform(
            lambda x: x.shift(-1).div(x).sub(1).mul(100)
        )
    )

    # Target:
    #  1 = UP
    #  0 = DOWN
    # -1 = SIDEWAYS

    df["Target"] = np.select(
        [
            df["NextDayReturnPct"] > 0.25,
            df["NextDayReturnPct"] < -0.25,
        ],
        [
            1,
            0,
        ],
        default=-1
    )

    # Last observation for each symbol has no next-day result.
    df.loc[
        df["NextDayReturnPct"].isna(),
        "Target"
    ] = np.nan

    return df


# ============================================================
# MAIN DATASET BUILDER
# ============================================================

def main():

    print("\n========================================")
    print("       LIVEQUANT-AI NSE DATA BUILDER")
    print("========================================\n")

    zip_files = sorted(RAW_DIR.glob("*.zip"))

    if not zip_files:

        raise FileNotFoundError(
            f"No NSE ZIP files found in: {RAW_DIR}"
        )

    print(f"ZIP files found: {len(zip_files)}")

    all_frames = []

    for index, zip_path in enumerate(zip_files, start=1):

        print(
            f"[{index}/{len(zip_files)}] "
            f"Reading {zip_path.name}"
        )

        frame = read_nse_zip(zip_path)

        if not frame.empty:
            all_frames.append(frame)

    if not all_frames:

        raise ValueError(
            "No valid NSE equity records were loaded."
        )

    # Combine all trading sessions.
    data = pd.concat(
        all_frames,
        ignore_index=True
    )

    # Remove duplicate observations.
    data = data.drop_duplicates(
        subset=["Date", "Symbol"],
        keep="last"
    )

    data = data.sort_values(
        ["Symbol", "Date"]
    ).reset_index(drop=True)

    # Validate date values.
    data = data.dropna(subset=["Date"])

    if data.empty:
        raise ValueError("No valid trading dates found.")

    # Add indicators.
    data = add_technical_indicators(data)

    # Add ML targets.
    data = add_prediction_targets(data)

    # Save ISO date strings.
    data["Date"] = data["Date"].dt.strftime("%Y-%m-%d")

    # History file.
    history_columns = [
        "Date",
        "Symbol",
        "Series",
        "Open",
        "High",
        "Low",
        "Close",
        "PreviousClose",
        "Volume",
        "TradedValue",
        "TotalTrades",
        "DailyReturnPct",
    ]

    history = data[
        history_columns
    ].copy()

    # Feature file.
    feature_columns = [
        "Date",
        "Symbol",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "TradedValue",
        "TotalTrades",
        "DailyReturnPct",
        "SMA_5",
        "SMA_20",
        "EMA_12",
        "EMA_26",
        "RSI_14",
        "MACD",
        "MACD_Signal",
        "MACD_Histogram",
        "NextDayReturnPct",
        "Target",
    ]

    features = data[
        feature_columns
    ].copy()

    # Save files without overwriting previous versions.
    history.to_csv(
        HISTORY_OUTPUT,
        index=False
    )

    features.to_csv(
        FEATURES_OUTPUT,
        index=False
    )

    # Summary.
    unique_dates = sorted(
        data["Date"].dropna().unique().tolist()
    )

    summary = {
        "project": "LIVEQUANT-AI",
        "dataset": "NSE Equity Historical Bhavcopy",
        "date_column_used": "BizDt",
        "total_records": int(len(data)),
        "unique_symbols": int(data["Symbol"].nunique()),
        "trading_sessions": int(data["Date"].nunique()),
        "first_date": str(unique_dates[0]),
        "last_date": str(unique_dates[-1]),
        "history_file": str(HISTORY_OUTPUT),
        "features_file": str(FEATURES_OUTPUT),
        "target_mapping": {
            "1": "UP",
            "0": "DOWN",
            "-1": "SIDEWAYS",
        },
    }

    with open(
        SUMMARY_OUTPUT,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            summary,
            file,
            indent=4
        )

    # Final output.
    print("\n========================================")
    print("          DATASET BUILD COMPLETE")
    print("========================================")

    print(f"Total records: {len(data):,}")
    print(f"Unique symbols: {data['Symbol'].nunique():,}")
    print(f"Trading sessions: {data['Date'].nunique()}")

    print(f"First date: {unique_dates[0]}")
    print(f"Last date: {unique_dates[-1]}")

    print("\nGenerated files:")

    print(HISTORY_OUTPUT)
    print(FEATURES_OUTPUT)
    print(SUMMARY_OUTPUT)

    print("\nDate validation:")

    if unique_dates[0] < "2026-09-01":
        warnings.warn(
            "Earliest date is before September 2026. "
            "Check the source ZIP files."
        )

    if unique_dates[-1] > "2026-11-30":
        warnings.warn(
            "Latest date is after November 2026. "
            "Check the source ZIP files."
        )

    print("\nNext step: connect corrected NSE data to FastAPI.")


if __name__ == "__main__":
    main()

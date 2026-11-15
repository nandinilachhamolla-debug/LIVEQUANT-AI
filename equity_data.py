from pathlib import Path
import json
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "extracted"
OUTPUT_DIR = ROOT / "data" / "processed"

REQUIRED_COLUMNS = [
    "TradDt",
    "TckrSymb",
    "SctySrs",
    "FinInstrmNm",
    "ISIN",
    "OpnPric",
    "HghPric",
    "LwPric",
    "ClsPric",
    "PrvsClsgPric",
    "TtlTradgVol",
    "TtlTrfVal",
    "TtlNbOfTxsExctd",
]


def find_latest_bhavcopy():
    files = sorted(
        RAW_DIR.glob("BhavCopy_NSE_CM_*.csv"),
        reverse=True
    )

    if not files:
        raise FileNotFoundError(
            f"No NSE bhavcopy CSV found in {RAW_DIR}"
        )

    return files[0]


def load_nse_data(file_path):
    print(f"\nReading NSE file: {file_path.name}")

    df = pd.read_csv(file_path)

    missing = [
        column for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required NSE columns: {missing}"
        )

    print(f"Original records: {len(df)}")

    return df


def prepare_equity_data(df):
    # Keep the NSE EQ security series.
    # This is the EQ series, not a guarantee that
    # every instrument is an ordinary company share.
    equity = df[
        df["SctySrs"].astype(str).str.strip() == "EQ"
    ].copy()

    print(f"EQ-series records: {len(equity)}")

    numeric_columns = [
        "OpnPric",
        "HghPric",
        "LwPric",
        "ClsPric",
        "PrvsClsgPric",
        "TtlTradgVol",
        "TtlTrfVal",
        "TtlNbOfTxsExctd",
    ]

    for column in numeric_columns:
        equity[column] = pd.to_numeric(
            equity[column],
            errors="coerce"
        )

    equity["TradDt"] = pd.to_datetime(
        equity["TradDt"],
        errors="coerce"
    )

    before = len(equity)

    # Remove records with missing essential fields.
    essential = [
        "TradDt",
        "TckrSymb",
        "OpnPric",
        "HghPric",
        "LwPric",
        "ClsPric",
        "TtlTradgVol",
    ]

    equity = equity.dropna(subset=essential)

    print(
        f"Removed missing essential values: "
        f"{before - len(equity)}"
    )

    # Prices must be positive.
    price_columns = [
        "OpnPric",
        "HghPric",
        "LwPric",
        "ClsPric",
    ]

    valid_prices = (
        (equity[price_columns] > 0).all(axis=1)
    )

    equity = equity[valid_prices].copy()

    # Volume cannot be negative.
    equity = equity[
        equity["TtlTradgVol"] >= 0
    ].copy()

    # Validate OHLC consistency.
    valid_ohlc = (
        (equity["HghPric"] >= equity["LwPric"])
        & (equity["HghPric"] >= equity["OpnPric"])
        & (equity["HghPric"] >= equity["ClsPric"])
        & (equity["LwPric"] <= equity["OpnPric"])
        & (equity["LwPric"] <= equity["ClsPric"])
    )

    invalid_ohlc = len(equity) - int(valid_ohlc.sum())
    equity = equity[valid_ohlc].copy()

    print(f"Removed invalid OHLC records: {invalid_ohlc}")

    # Standardise column names for our AI pipeline.
    equity = equity.rename(
        columns={
            "TradDt": "Date",
            "TckrSymb": "Symbol",
            "FinInstrmNm": "SecurityName",
            "SctySrs": "Series",
            "OpnPric": "Open",
            "HghPric": "High",
            "LwPric": "Low",
            "ClsPric": "Close",
            "PrvsClsgPric": "PreviousClose",
            "TtlTradgVol": "Volume",
            "TtlTrfVal": "Turnover",
            "TtlNbOfTxsExctd": "NumberOfTrades",
        }
    )

    output_columns = [
        "Date",
        "Symbol",
        "SecurityName",
        "ISIN",
        "Series",
        "Open",
        "High",
        "Low",
        "Close",
        "PreviousClose",
        "Volume",
        "Turnover",
        "NumberOfTrades",
    ]

    equity = equity[output_columns].copy()

    equity["Date"] = equity["Date"].dt.strftime(
        "%Y-%m-%d"
    )

    equity = equity.sort_values(
        ["Symbol", "Date"]
    )

    equity = equity.drop_duplicates(
        subset=["Date", "Symbol"],
        keep="last"
    )

    return equity.reset_index(drop=True)


def save_outputs(equity, source_file):
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    output_file = (
        OUTPUT_DIR /
        f"nse_equity_{source_file.stem[-9:]}.csv"
    )

    equity.to_csv(output_file, index=False)

    summary = {
        "project": "LIVEQUANT AI",
        "source": source_file.name,
        "records": int(len(equity)),
        "unique_symbols": int(equity["Symbol"].nunique()),
        "trading_dates": sorted(
            equity["Date"].dropna().unique().tolist()
        ),
        "columns": equity.columns.tolist(),
        "data_type": "NSE EQ-series bhavcopy records",
        "live_connection": False,
    }

    summary_file = OUTPUT_DIR / "equity_data_summary.json"

    with open(summary_file, "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=4)

    print("\n========== DATASET SUMMARY ==========")
    print(f"Clean records: {len(equity)}")
    print(f"Unique symbols: {equity['Symbol'].nunique()}")
    print(f"Output CSV: {output_file}")
    print(f"Summary JSON: {summary_file}")

    print("\nFirst 10 cleaned records:")
    print(equity.head(10).to_string(index=False))

    return output_file


def main():
    source_file = find_latest_bhavcopy()
    raw_data = load_nse_data(source_file)

    equity = prepare_equity_data(raw_data)

    if equity.empty:
        raise ValueError(
            "No valid EQ-series records remained after validation."
        )

    save_outputs(equity, source_file)

    print("\nNSE EQUITY DATA PIPELINE COMPLETED.")


if __name__ == "__main__":
    main()

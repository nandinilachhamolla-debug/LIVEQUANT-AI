
from pathlib import Path
import json
import warnings

import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    balanced_accuracy_score,
    confusion_matrix,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parent.parent

DATA_FILE = ROOT / "data" / "processed" / "nse_equity_features_v3.csv"
MODEL_DIR = ROOT / "models"

MODEL_DIR.mkdir(parents=True, exist_ok=True)

LOGISTIC_PATH = MODEL_DIR / "equity_logistic_v1.joblib"
FOREST_PATH = MODEL_DIR / "equity_random_forest_v1.joblib"
ANOMALY_PATH = MODEL_DIR / "equity_isolation_forest_v1.joblib"
REPORT_PATH = MODEL_DIR / "equity_training_report_v1.json"

FEATURES = [
    "DailyReturnPct",
    "SMA_5",
    "EMA_12",
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "TradedValue",
    "TotalTrades",
]

TARGET = "Target"

# Mapping:
# 0 = DOWN
# 1 = UP
# 2 = SIDEWAYS
LABEL_MAP = {
    0.0: 0,
    1.0: 1,
    -1.0: 2,
}

CLASS_NAMES = ["DOWN", "UP", "SIDEWAYS"]


def load_dataset():

    if not DATA_FILE.exists():
        raise FileNotFoundError(DATA_FILE)

    df = pd.read_csv(DATA_FILE)

    required = FEATURES + [TARGET, "Date", "Symbol"]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(f"Missing columns: {missing}")

    df["Date"] = pd.to_datetime(
        df["Date"],
        errors="coerce"
    )

    for col in FEATURES + [TARGET]:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = df.dropna(
        subset=["Date", "Symbol", TARGET]
    ).copy()

    df = df[df[TARGET].isin(LABEL_MAP)].copy()

    df["TargetClass"] = (
        df[TARGET].map(LABEL_MAP).astype(int)
    )

    df = df.sort_values(
        ["Date", "Symbol"]
    ).reset_index(drop=True)

    if df["Date"].nunique() < 10:
        raise ValueError(
            "Not enough unique dates for chronological testing."
        )

    return df


def chronological_split(df):

    dates = sorted(df["Date"].unique())

    split_index = int(len(dates) * 0.8)

    split_index = max(
        1,
        min(split_index, len(dates) - 1)
    )

    train_dates = dates[:split_index]
    test_dates = dates[split_index:]

    train = df[df["Date"].isin(train_dates)].copy()
    test = df[df["Date"].isin(test_dates)].copy()

    return train, test


def build_pipeline(model):

    return Pipeline([
        (
            "imputer",
            SimpleImputer(
                strategy="median",
                add_indicator=True
            )
        ),
        (
            "scaler",
            StandardScaler()
        ),
        (
            "model",
            model
        ),
    ])


def evaluate_model(name, model, X_test, y_test):

    predictions = model.predict(X_test)

    return {
        "model": name,
        "accuracy": float(
            accuracy_score(y_test, predictions)
        ),
        "balanced_accuracy": float(
            balanced_accuracy_score(
                y_test,
                predictions
            )
        ),
        "confusion_matrix": confusion_matrix(
            y_test,
            predictions,
            labels=[0, 1, 2]
        ).tolist(),
        "classification_report": classification_report(
            y_test,
            predictions,
            labels=[0, 1, 2],
            target_names=CLASS_NAMES,
            output_dict=True,
            zero_division=0,
        ),
        "test_predictions": int(len(predictions)),
    }


def main():

    print("\n===================================")
    print(" LIVEQUANT-AI NSE MODEL TRAINING")
    print("===================================\n")

    df = load_dataset()

    train, test = chronological_split(df)

    X_train = train[FEATURES]
    y_train = train["TargetClass"]

    X_test = test[FEATURES]
    y_test = test["TargetClass"]

    print("Total records:", len(df))
    print("Training records:", len(train))
    print("Testing records:", len(test))
    print("Training dates:", train["Date"].nunique())
    print("Testing dates:", test["Date"].nunique())

    if y_train.nunique() < 3:
        raise ValueError(
            "Training data does not contain all three classes."
        )

    if y_test.nunique() < 3:
        warnings.warn(
            "The test period does not contain all three classes."
        )

    # Logistic Regression baseline.
    logistic = build_pipeline(
        LogisticRegression(
            max_iter=1500,
            class_weight="balanced",
            random_state=42,
        )
    )

    print("\nTraining Logistic Regression...")

    logistic.fit(X_train, y_train)

    logistic_report = evaluate_model(
        "Logistic Regression",
        logistic,
        X_test,
        y_test
    )

    joblib.dump(logistic, LOGISTIC_PATH)

    # Random Forest.
    forest = build_pipeline(
        RandomForestClassifier(
            n_estimators=150,
            max_depth=10,
            min_samples_leaf=5,
            class_weight="balanced_subsample",
            random_state=42,
            n_jobs=-1,
        )
    )

    print("Training Random Forest...")

    forest.fit(X_train, y_train)

    forest_report = evaluate_model(
        "Random Forest",
        forest,
        X_test,
        y_test
    )

    joblib.dump(forest, FOREST_PATH)

    # Isolation Forest: anomaly detection only.
    print("Training Isolation Forest...")

    anomaly_imputer = SimpleImputer(
        strategy="median"
    )

    anomaly_X = anomaly_imputer.fit_transform(
        df[FEATURES]
    )

    anomaly_model = IsolationForest(
        n_estimators=150,
        contamination="auto",
        random_state=42,
        n_jobs=-1,
    )

    anomaly_model.fit(anomaly_X)

    joblib.dump(
        {
            "imputer": anomaly_imputer,
            "model": anomaly_model,
            "features": FEATURES,
        },
        ANOMALY_PATH
    )

    # Compare classifiers using balanced accuracy.
    reports = [
        logistic_report,
        forest_report
    ]

    best = max(
        reports,
        key=lambda item: item["balanced_accuracy"]
    )

    report = {
        "project": "LIVEQUANT-AI",
        "dataset": str(DATA_FILE),
        "total_records": len(df),
        "symbols": int(df["Symbol"].nunique()),
        "total_dates": int(df["Date"].nunique()),
        "train_records": len(train),
        "test_records": len(test),
        "train_first_date": str(train["Date"].min().date()),
        "train_last_date": str(train["Date"].max().date()),
        "test_first_date": str(test["Date"].min().date()),
        "test_last_date": str(test["Date"].max().date()),
        "features": FEATURES,
        "classes": CLASS_NAMES,
        "logistic_regression": logistic_report,
        "random_forest": forest_report,
        "selected_model": best["model"],
        "selected_model_reason": "Highest chronological test balanced accuracy",
        "warning": (
            "Experimental model. Only 30 original trading sessions "
            "are available. Results do not establish reliable future "
            "predictive performance."
        ),
    }

    with open(
        REPORT_PATH,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            report,
            file,
            indent=4,
            default=str
        )

    print("\n===================================")
    print(" MODEL TRAINING COMPLETE")
    print("===================================")

    for item in reports:
        print("\n", item["model"])
        print("Accuracy:", round(item["accuracy"], 4))
        print(
            "Balanced accuracy:",
            round(item["balanced_accuracy"], 4)
        )

    print("\nSelected model:", best["model"])
    print("\nSaved models:")
    print(LOGISTIC_PATH)
    print(FOREST_PATH)
    print(ANOMALY_PATH)
    print(REPORT_PATH)

    print("\nThese are experimental research models,")
    print("not guaranteed market predictions.")


if __name__ == "__main__":
    main()

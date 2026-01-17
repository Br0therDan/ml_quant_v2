import json
import logging
from datetime import datetime

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score

from ..config import settings
from ..db.metastore import MetaStore
from ..db.timeseries import SeriesStore
from ..ml.experts import detect_market_regime, get_regime_label
from ..ml.splits import get_time_series_splits
from ..models.meta import Model

logger = logging.getLogger(__name__)


class StabilitySelector:
    """Perform stability selection to find robust features."""

    def select(
        self, X: pd.DataFrame, y: pd.Series, n_runs: int = 10, top_n: int = 20
    ) -> list[str]:
        feature_counts = dict.fromkeys(X.columns, 0)

        for _ in range(n_runs):
            # 70% Subsample
            sample_idx = np.random.choice(
                X.index, size=int(len(X) * 0.7), replace=False
            )
            X_sub = X.loc[sample_idx]
            y_sub = y.loc[sample_idx]

            model = lgb.LGBMClassifier(n_estimators=50, learning_rate=0.1, verbose=-1)
            model.fit(X_sub, y_sub)

            # Feature importance based on Gain
            importances = pd.Series(model.feature_importances_, index=X.columns)
            top_features = importances.nlargest(top_n).index.tolist()

            for f in top_features:
                feature_counts[f] += 1

        sr_counts = pd.Series(feature_counts)
        return sr_counts.nlargest(top_n).index.tolist()


class MLTrainer:
    def __init__(
        self,
        series_store: SeriesStore | None = None,
        meta_store: MetaStore | None = None,
    ):
        self.series_store = series_store or SeriesStore()
        self.meta_store = meta_store or MetaStore()
        self.model_dir = Path(settings.repo_root) / "artifacts" / "models"
        self.model_dir.mkdir(parents=True, exist_ok=True)

    def prepare_data(
        self, symbol: str, feature_version: str = "v1", label_version: str = "v1"
    ) -> pd.DataFrame:
        df_feat = self.series_store.get_features(symbol, version=feature_version)
        df_label = self.series_store.get_labels(symbol, version=label_version)

        if df_feat.empty or df_label.empty:
            return pd.DataFrame()

        return df_feat.join(df_label, how="inner")

    def train_baseline(
        self,
        symbol: str,
        feature_version: str = "v1",
        label_version: str = "v1",
        horizon: int = 60,
        feature_selection: bool = False,
        stability_n_runs: int = 10,
    ) -> str | None:
        df = self.prepare_data(symbol, feature_version, label_version)
        if df.empty:
            logger.warning(f"No data for {symbol}. Skipping train.")
            return None

        label_col = f"direction_{horizon}d"
        if label_col not in df.columns:
            logger.warning(f"Label {label_col} not found for {symbol}. Skipping.")
            return None

        feature_cols = [
            c
            for c in df.columns
            if not c.startswith("direction_")
            and not c.startswith("fwd_ret_")
            and c != "regime"
        ]

        splits = get_time_series_splits(
            df.index, n_splits=1, train_size=500, test_size=100, gap=horizon
        )
        if not splits:
            logger.warning(f"Not enough data for splitting {symbol}. Skipping.")
            return None

        train_dates, test_dates = splits[0]
        X_train, y_train = (
            df.loc[train_dates, feature_cols],
            df.loc[train_dates, label_col],
        )
        X_test, y_test = df.loc[test_dates, feature_cols], df.loc[test_dates, label_col]

        if feature_selection:
            selector = StabilitySelector()
            selected_features = selector.select(
                X_train, y_train, n_runs=stability_n_runs
            )
            X_train = X_train[selected_features]
            X_test = X_test[selected_features]

        model = lgb.LGBMClassifier(
            n_estimators=100, learning_rate=0.05, importance_type="gain", verbose=-1
        )
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, zero_division=0)

        model_id = f"lgb_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        model_path = self.model_dir / f"{model_id}.joblib"
        joblib.dump(model, model_path)

        with self.meta_store.get_session() as session:
            new_model = Model(
                model_id=model_id,
                experiment_id="baseline_v1",
                algo="LightGBM",
                feature_version=feature_version,
                label_version=label_version,
                params_json=json.dumps({"n_estimators": 100, "learning_rate": 0.05}),
                metrics_json=json.dumps(
                    {"accuracy": float(acc), "precision": float(prec)}
                ),
                created_at=datetime.utcnow().isoformat(),
            )
            # Store model file path in a predictable way for V2 or add field if needed
            # For now we use artifacts/models/ as base
            session.add(new_model)
            session.commit()

        logger.info(f"Model {model_id} saved. (Acc: {acc:.4f}, Prec: {prec:.4f})")
        return model_id

    def train_experts(
        self,
        symbol: str,
        benchmark_symbol: str = "QQQ",
        feature_version: str = "v1",
        label_version: str = "v1",
        horizon: int = 60,
    ) -> list[str]:
        df = self.prepare_data(symbol, feature_version, label_version)
        if df.empty:
            return []

        df_bench = self.series_store.get_ohlcv(benchmark_symbol)
        if df_bench.empty:
            logger.warning(f"Benchmark {benchmark_symbol} missing.")
            return []

        regimes = detect_market_regime(df_bench)
        df = df.join(regimes, how="inner")

        label_col = f"direction_{horizon}d"
        feature_cols = [
            c
            for c in df.columns
            if not c.startswith("direction_")
            and not c.startswith("fwd_ret_")
            and c != "regime"
        ]

        model_ids = []
        for regime_val in [1.0, -1.0]:
            regime_name = get_regime_label(regime_val)
            df_sub = df[df["regime"] == regime_val]

            if len(df_sub) < 100:
                continue

            splits = get_time_series_splits(
                df_sub.index,
                n_splits=1,
                train_size=int(len(df_sub) * 0.8),
                test_size=min(100, int(len(df_sub) * 0.1)),
                gap=horizon,
            )
            if not splits:
                continue

            train_dates, test_dates = splits[0]
            X_train, y_train = (
                df_sub.loc[train_dates, feature_cols],
                df_sub.loc[train_dates, label_col],
            )
            X_test, y_test = (
                df_sub.loc[test_dates, feature_cols],
                df_sub.loc[test_dates, label_col],
            )

            model = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, verbose=-1)
            model.fit(X_train, y_train)

            acc = accuracy_score(y_test, model.predict(X_test))

            model_id = f"expert_{regime_name}_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            path = self.model_dir / f"{model_id}.joblib"
            joblib.dump(model, path)

            with self.meta_store.get_session() as session:
                new_model = Model(
                    model_id=model_id,
                    experiment_id=f"{regime_name}_expert_v1",
                    algo=f"LightGBM-Expert-{regime_name}",
                    feature_version=feature_version,
                    label_version=label_version,
                    params_json=json.dumps({"regime": regime_name}),
                    metrics_json=json.dumps({"accuracy": float(acc)}),
                )
                session.add(new_model)
                session.commit()

            model_ids.append(model_id)

        return model_ids

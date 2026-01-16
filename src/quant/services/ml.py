import logging
import pandas as pd
import numpy as np
import os
import joblib
from datetime import datetime
from typing import List, Optional, Tuple, Any

from quant.db.timeseries import SeriesStore
from quant.db.metastore import MetaStore
from quant.models import Symbol, Model
from quant.ml.splits import get_time_series_splits
from quant.ml.experts import detect_market_regime, get_regime_label
import json

log = logging.getLogger(__name__)


class MLService:
    def __init__(
        self,
        series_store: Optional[SeriesStore] = None,
        meta_store: Optional[MetaStore] = None,
    ):
        self.series_store = series_store or SeriesStore()
        self.meta_store = meta_store or MetaStore()
        self.model_dir = "models"
        os.makedirs(self.model_dir, exist_ok=True)

    def prepare_data(
        self, symbol: str, feature_version: str = "v1", label_version: str = "v1"
    ) -> pd.DataFrame:
        """
        특징량과 레이블을 Join하여 데이터프레임을 생성합니다.
        """
        df_feat = self.series_store.get_features(symbol, version=feature_version)
        df_label = self.series_store.get_labels(symbol, version=label_version)

        if df_feat.empty or df_label.empty:
            return pd.DataFrame()

        # Join on date
        df = df_feat.join(df_label, how="inner")
        return df

    def train_baseline(
        self,
        symbol: str,
        feature_version: str = "v1",
        label_version: str = "v1",
        horizon: int = 60,
        feature_selection: bool = False,
        stability_n_runs: int = 10,
    ) -> Optional[str]:
        """
        LightGBM 베이스라인 모델을 학습하고 SQLite 레지스트리에 기록합니다.
        Optional: Stability Selection을 수행하여 피처를 선별합니다.
        """
        import lightgbm as lgb
        from sklearn.metrics import accuracy_score, precision_score

        df = self.prepare_data(symbol, feature_version, label_version)
        if df.empty:
            log.warning(f"No data for {symbol}. Skipping train.")
            return None

        # 레이블 컬럼명 식별
        label_col = f"direction_{horizon}d"
        if label_col not in df.columns:
            log.warning(f"Label {label_col} not found in data. Skipping.")
            return None

        # 특징량 목록 (레이블 제외 모든 컬럼)
        feature_cols = [
            c
            for c in df.columns
            if not c.startswith("direction_")
            and not c.startswith("fwd_ret_")
            and c != "regime"
        ]

        # 데이터 분할 (최신 1년 학습, 다음 60일 검증 형태의 마지막 스플릿 사용)
        splits = get_time_series_splits(
            df.index, n_splits=1, train_size=500, test_size=100, gap=horizon
        )
        if not splits:
            log.warning(f"Not enough data for splitting {symbol}. Skipping.")
            return None

        train_dates, test_dates = splits[0]
        X_train, y_train = (
            df.loc[train_dates, feature_cols],
            df.loc[train_dates, label_col],
        )
        X_test, y_test = df.loc[test_dates, feature_cols], df.loc[test_dates, label_col]

        # Feature Selection (Optional)
        selected_features = feature_cols
        if feature_selection:
            log.info(
                f"Performing stability selection for {symbol} (runs={stability_n_runs})..."
            )
            selected_features = self.perform_stability_selection(
                X_train, y_train, n_runs=stability_n_runs
            )
            log.info(
                f"Selected {len(selected_features)} features out of {len(feature_cols)}."
            )
            X_train = X_train[selected_features]
            X_test = X_test[selected_features]

        log.info(f"Training LightGBM for {symbol}... (Train rows: {len(X_train)})")

        log.info(f"Training LightGBM for {symbol}... (Train rows: {len(X_train)})")

        # 모델 학습
        model = lgb.LGBMClassifier(
            n_estimators=100, learning_rate=0.05, importance_type="gain", verbose=-1
        )
        model.fit(X_train, y_train)

        # 평가
        y_pred = model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, zero_division=0)

        # 모델 메타 정보 생성
        model_id = f"lgb_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        model_path = os.path.join(self.model_dir, f"{model_id}.joblib")
        joblib.dump(model, model_path)

        # SQLite 기록
        import json

        with self.meta_store.get_session() as session:
            new_model = Model(
                model_id=model_id,
                symbol=symbol,
                algo="LightGBM",
                feature_version=feature_version,
                label_version=label_version,
                params_json=json.dumps({"n_estimators": 100, "learning_rate": 0.05}),
                metrics_json=json.dumps(
                    {"accuracy": float(acc), "precision": float(prec)}
                ),
                path=model_path,
                is_active=True,
            )
            session.add(new_model)
            session.commit()

        log.info(
            f"Model {model_id} saved and registered. (Acc: {acc:.4f}, Prec: {prec:.4f})"
        )
        return model_id

    def train_experts(
        self,
        symbol: str,
        benchmark_symbol: str = "QQQ",
        feature_version: str = "v1",
        label_version: str = "v1",
        horizon: int = 60,
    ) -> List[str]:
        """
        시장 국면(Bull/Bear)별 전문가 모델을 각각 학습합니다.
        """
        import lightgbm as lgb
        from sklearn.metrics import accuracy_score

        # 1. 데이터 준비
        df = self.prepare_data(symbol, feature_version, label_version)
        if df.empty:
            return []

        # 2. 벤치마크 기반 국면 진단
        df_bench_ohlcv = self.series_store.get_ohlcv(benchmark_symbol)
        if df_bench_ohlcv.empty:
            log.warning(
                f"Benchmark {benchmark_symbol} data not found. Skipping Experts."
            )
            return []

        regimes = detect_market_regime(df_bench_ohlcv)
        df = df.join(regimes, how="inner")

        # 3. 공통 설정
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
                log.warning(
                    f"Not enough data for {regime_name} regime ({len(df_sub)} rows). Skipping."
                )
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

            log.info(
                f"Training {regime_name} expert for {symbol}... (Rows: {len(X_train)})"
            )

            model = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, verbose=-1)
            model.fit(X_train, y_train)

            acc = accuracy_score(y_test, model.predict(X_test))

            model_id = f"expert_{regime_name}_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            path = os.path.join(self.model_dir, f"{model_id}.joblib")
            joblib.dump(model, path)

            with self.meta_store.get_session() as session:
                new_model = Model(
                    model_id=model_id,
                    symbol=symbol,
                    algo=f"LightGBM-Expert-{regime_name}",
                    experiment_id=f"{regime_name}_expert_v1",
                    feature_version=feature_version,
                    label_version=label_version,
                    params_json=json.dumps(
                        {"regime": regime_name, "n_estimators": 100}
                    ),
                    metrics_json=json.dumps({"accuracy": float(acc)}),
                    path=path,
                    is_active=True,
                )
                session.add(new_model)
                session.commit()

            model_ids.append(model_id)
            log.info(f"Expert {model_id} registered. (Acc: {acc:.4f})")

        return model_ids

    def score_ensemble(self, symbol: str, benchmark_symbol: str = "QQQ"):
        """
        시장 상황에 맞는 전문가 모델을 선택(Gating)하여 예측 점수를 생성합니다.
        """
        # 1. 벤치마크 국면 진단
        df_bench = self.series_store.get_ohlcv(benchmark_symbol)
        if df_bench.empty:
            return
        regimes = detect_market_regime(df_bench)

        # 2. 최신 전문가 모델 로드
        experts = {}
        with self.meta_store.get_session() as session:
            from sqlmodel import select

            for rname in ["bull", "bear"]:
                stmt = (
                    select(Model)
                    .where(
                        Model.symbol == symbol,
                        Model.experiment_id == f"{rname}_expert_v1",
                        Model.is_active == True,
                    )
                    .order_by(Model.created_at.desc())
                )
                m = session.exec(stmt).first()
                if m:
                    experts[rname] = m

        if not experts:
            log.warning(
                f"No experts found for {symbol}. Run train --task experts first."
            )
            return

        # 3. 수집된 특징량 로드
        # 공통 버전 사용 (v1 가정)
        any_model = list(experts.values())[0]
        df_feat = self.series_store.get_features(
            symbol, version=any_model.feature_version
        )
        if df_feat.empty:
            return

        # 4. 날짜별로 국면에 맞는 전문가 적용
        df_score = df_feat.join(regimes, how="inner").dropna(subset=["regime"])

        final_preds = []
        # 성능을 위해 국면별로 배치 처리
        for rname in ["bull", "bear"]:
            if rname not in experts:
                continue

            rval = 1.0 if rname == "bull" else -1.0
            idx_sub = df_score[df_score["regime"] == rval].index
            if idx_sub.empty:
                continue

            m_info = experts[rname]
            model = joblib.load(m_info.path)
            X = df_score.loc[idx_sub, model.feature_name_]

            probs = model.predict_proba(X)[:, 1]

            df_res_sub = pd.DataFrame(
                {
                    "symbol": symbol,
                    "date": idx_sub,
                    "model_id": m_info.model_id,
                    "task_id": "expert_ensemble",
                    "score": probs,
                }
            )
            final_preds.append(df_res_sub)

        if final_preds:
            df_final = pd.concat(final_preds).sort_values("date")
            self.series_store.save_predictions(df_final)
            log.info(f"Ensemble score saved for {symbol} ({len(df_final)} rows)")

    def score(self, symbol: str, model_id: Optional[str] = None):
        """
        학습된 모델로 예측 결과를 생성하고 DuckDB에 저장합니다.
        """
        # 모델 정보 로드
        with self.meta_store.get_session() as session:
            from sqlmodel import select

            if model_id:
                statement = select(Model).where(Model.model_id == model_id)
            else:
                statement = (
                    select(Model)
                    .where(Model.symbol == symbol, Model.is_active == True)
                    .order_by(Model.created_at.desc())
                )

            db_model = session.exec(statement).first()
            if not db_model:
                log.warning(f"No active model found for {symbol}. Skipping score.")
                return

        model = joblib.load(db_model.path)
        df_feat = self.series_store.get_features(
            symbol, version=db_model.feature_version
        )

        if df_feat.empty:
            log.warning(f"No features found for {symbol}. Skipping score.")
            return

        # Inference
        feature_cols = model.feature_name_
        df_scoring = df_feat[feature_cols].dropna()
        if df_scoring.empty:
            log.warning(f"No valid scoring data for {symbol} after dropna. Skipping.")
            return

        preds = model.predict_proba(df_scoring)[:, 1]  # Probability of Class 1 (Up)

        # Result DataFrame
        df_res = pd.DataFrame(
            {
                "symbol": symbol,
                "date": df_scoring.index,
                "model_id": db_model.model_id,
                "task_id": "daily_pred",
                "score": preds,
            }
        )

        # Save to DuckDB
        self.series_store.save_predictions(df_res)
        log.info(
            f"Saved {len(df_res)} predictions for {symbol} using {db_model.model_id}"
        )

    def perform_stability_selection(
        self, X: pd.DataFrame, y: pd.Series, n_runs: int = 10, top_n: int = 20
    ) -> List[str]:
        """
        반복적인 Subsampling & Training을 통해 안정적인 피처를 선별합니다.
        """
        import lightgbm as lgb

        feature_counts = {col: 0 for col in X.columns}

        for i in range(n_runs):
            # 70% Subsample
            sample_idx = np.random.choice(
                X.index, size=int(len(X) * 0.7), replace=False
            )
            X_sub = X.loc[sample_idx]
            y_sub = y.loc[sample_idx]

            model = lgb.LGBMClassifier(n_estimators=50, learning_rate=0.1, verbose=-1)
            model.fit(X_sub, y_sub)

            # 피처 중요도(Gain) 기준 상위 Top-N 확인
            importances = pd.Series(model.feature_importances_, index=X.columns)
            top_features = importances.nlargest(top_n).index.tolist()

            for f in top_features:
                feature_counts[f] += 1

        # 50% 이상 선택된 피처만 반환 (또는 상위 Top-N 고정)
        # 여기서는 빈도수 기준 상위 Top-N
        sr_counts = pd.Series(feature_counts)
        final_features = sr_counts.nlargest(top_n).index.tolist()

        return final_features

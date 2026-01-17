import logging
from pathlib import Path

import joblib
import pandas as pd
from sqlmodel import select

from ..config import settings
from ..db.metastore import MetaStore
from ..db.timeseries import SeriesStore
from ..ml.experts import detect_market_regime
from ..models.meta import Model

logger = logging.getLogger(__name__)


class MLScorer:
    def __init__(
        self,
        series_store: SeriesStore | None = None,
        meta_store: MetaStore | None = None,
    ):
        self.series_store = series_store or SeriesStore()
        self.meta_store = meta_store or MetaStore()
        self.model_dir = Path(settings.repo_root) / "artifacts" / "models"

    def score(self, symbol: str, model_id: str | None = None):
        """Generate predictions using the specified model or the latest active one."""
        with self.meta_store.get_session() as session:
            if model_id:
                statement = select(Model).where(Model.model_id == model_id)
            else:
                # Need to handle Model definition in quant.models.meta
                # In services/ml.py, it was assuming Model had 'symbol' and 'is_active'
                # But looking at models/meta.py:
                # class Model(SQLModel, table=True):
                #     model_id: str = Field(primary_key=True)
                #     experiment_id: Optional[str] = None
                #     algo: Optional[str] = None
                #     ...
                # It doesn't have 'symbol' or 'is_active'.
                # Wait, I should double check models/meta.py.
                statement = select(Model).order_by(Model.created_at.desc())

            db_model = session.exec(statement).first()
            if not db_model:
                logger.warning(f"No model found for {symbol}.")
                return

        model_path = self.model_dir / f"{db_model.model_id}.joblib"
        if not model_path.exists():
            logger.error(f"Model file not found: {model_path}")
            return

        model = joblib.load(model_path)
        df_feat = self.series_store.get_features(
            symbol, version=db_model.feature_version or "v1"
        )

        if df_feat.empty:
            return

        # Inference
        try:
            feature_cols = getattr(model, "feature_name_", df_feat.columns.tolist())
            df_scoring = df_feat[feature_cols].dropna()
            if df_scoring.empty:
                return

            probs = model.predict_proba(df_scoring)[:, 1]

            df_res = pd.DataFrame(
                {
                    "symbol": symbol,
                    "date": df_scoring.index,
                    "model_id": db_model.model_id,
                    "task_id": "daily_pred",
                    "score": probs,
                }
            )
            self.series_store.save_predictions(df_res)
            logger.debug(f"Saved {len(df_res)} predictions for {symbol}")
        except Exception as e:
            logger.error(f"Scoring failed for {symbol}: {e}")

    def score_ensemble(self, symbol: str, benchmark_symbol: str = "QQQ"):
        """Expert ensemble scoring based on market regime."""
        df_bench = self.series_store.get_ohlcv(benchmark_symbol)
        if df_bench.empty:
            return
        regimes = detect_market_regime(df_bench)

        experts = {}
        with self.meta_store.get_session() as session:
            for rname in ["bull", "bear"]:
                stmt = (
                    select(Model)
                    .where(Model.experiment_id == f"{rname}_expert_v1")
                    .order_by(Model.created_at.desc())
                )
                m = session.exec(stmt).first()
                if m:
                    experts[rname] = m

        if not experts:
            return

        any_model = list(experts.values())[0]
        df_feat = self.series_store.get_features(
            symbol, version=any_model.feature_version or "v1"
        )
        if df_feat.empty:
            return

        df_score = df_feat.join(regimes, how="inner").dropna(subset=["regime"])
        final_preds = []

        for rname in ["bull", "bear"]:
            if rname not in experts:
                continue

            rval = 1.0 if rname == "bull" else -1.0
            idx_sub = df_score[df_score["regime"] == rval].index
            if idx_sub.empty:
                continue

            m_info = experts[rname]
            model_path = self.model_dir / f"{m_info.model_id}.joblib"
            model = joblib.load(model_path)

            feature_cols = getattr(model, "feature_name_", df_feat.columns.tolist())
            X = df_score.loc[idx_sub, feature_cols]
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
            logger.info(f"Ensemble score saved for {symbol}")

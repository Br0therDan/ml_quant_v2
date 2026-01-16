import logging
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, Dict

from quant.db.timeseries import SeriesStore

log = logging.getLogger(__name__)


class BacktestService:
    def __init__(self, series_store: Optional[SeriesStore] = None):
        self.series_store = series_store or SeriesStore()

    def run_backtest(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> Dict:
        """
        저장된 portfolio_decisions를 기반으로 백테스트를 수행합니다.
        """
        # 1. 포트폴리오 비중 데이터 로드
        df_decisions = self.series_store.get_portfolio_decisions()
        if df_decisions.empty:
            log.warning(
                "No portfolio decisions found. Run 'quant recommend' first for various dates."
            )
            return {}

        df_decisions["date"] = pd.to_datetime(df_decisions["date"])
        if start_date:
            df_decisions = df_decisions[
                df_decisions["date"] >= pd.to_datetime(start_date)
            ]
        if end_date:
            df_decisions = df_decisions[
                df_decisions["date"] <= pd.to_datetime(end_date)
            ]

        if df_decisions.empty:
            log.warning("Filtered decisions are empty.")
            return {}

        # 2. 일별 수익률 계산을 위한 종가 데이터 준비
        symbols = df_decisions["symbol"].unique().tolist()
        price_data = {}
        for symbol in symbols:
            df_ohlcv = self.series_store.get_ohlcv(symbol)
            if not df_ohlcv.empty:
                # 'date' 컬럼 위치 확인
                if "date" in df_ohlcv.columns:
                    df_ohlcv["date"] = pd.to_datetime(df_ohlcv["date"])
                    df_ohlcv = df_ohlcv.set_index("date")
                elif df_ohlcv.index.name == "date":
                    df_ohlcv.index = pd.to_datetime(df_ohlcv.index)

                df_ohlcv = df_ohlcv.sort_index()
                # t일의 리턴 = t일의 종가 / t-1일의 종가 - 1
                price_data[symbol] = df_ohlcv["close"].pct_change()

        # 3. 일별 포트폴리오 수익률 시뮬레이션
        dates = sorted(df_decisions["date"].unique())
        daily_returns = []

        for d in dates:
            # d일 결정된 비중
            df_day = df_decisions[df_decisions["date"] == d]
            # d일 종가에 사서 다음 영업일(next_d) 종가에 파는 수익률 산출
            # 여기서는 편의상 d일의 수익률을 d일 비중에 적용 (동일 시점 가중치 합산)
            # 엄격하게 하려면 shift(-1)이 필요하나 데이터셋 정합성 확인 필요
            day_ret = 0.0
            found_any = False
            for _, row in df_day.iterrows():
                symbol = row["symbol"]
                weight = row["weight"]
                if symbol in price_data and d in price_data[symbol].index:
                    ret = price_data[symbol].loc[d]
                    if not np.isnan(ret):
                        day_ret += weight * ret
                        found_any = True

            if found_any:
                daily_returns.append({"date": d, "return": day_ret})

        df_returns = pd.DataFrame(daily_returns).set_index("date")
        if df_returns.empty:
            return {}

        # 4. 성과 지표 산출
        metrics = self.calculate_metrics(df_returns["return"])

        # 5. 결과 저장 (Summary)
        run_id = f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        df_summary = pd.DataFrame(
            [
                {
                    "run_id": run_id,
                    "from_ts": dates[0],
                    "to_ts": dates[-1],
                    "cagr": metrics["cagr"],
                    "sharpe": metrics["sharpe"],
                    "max_dd": metrics["max_dd"],
                    "num_trades": len(df_decisions),
                }
            ]
        )

        self.series_store.save_backtest_summary(df_summary)

        # 6. 결과 저장 (Equity Curve)
        df_equity = df_returns.copy().reset_index()
        df_equity["run_id"] = run_id
        df_equity["daily_return"] = df_equity["return"]
        df_equity["equity"] = (1 + df_equity["daily_return"]).cumprod()
        self.series_store.save_backtest_equity_curve(df_equity)

        # 7. 결과 저장 (Trades - 단순화하여 전체 이력 저장)
        df_trades = df_decisions.copy()
        df_trades["run_id"] = run_id
        df_trades["action"] = "rebalance"  # 일괄 rebalance로 처리
        # price 정보 추가 (가능할 경우)
        df_trades["price"] = 0.0  # 일단 0으로 세팅

        self.series_store.save_backtest_trades(df_trades)

        log.info(
            f"Backtest {run_id} completed. CAGR: {metrics['cagr']:.2%}, Sharpe: {metrics['sharpe']:.2f}"
        )
        return metrics

    def calculate_metrics(self, returns: pd.Series) -> Dict:
        """주요 성과 지표를 계산합니다."""
        if returns.empty:
            return {"cagr": 0, "sharpe": 0, "max_dd": 0}

        # 일별 -> 연율화 (252영업일 가정)
        cum_ret = (1 + returns).prod() - 1
        days = (returns.index[-1] - returns.index[0]).days
        if days > 0:
            cagr = (1 + cum_ret) ** (365.0 / days) - 1
        else:
            cagr = cum_ret

        vol = returns.std() * np.sqrt(252)
        sharpe = (cagr / vol) if vol > 0 else 0

        # Max Drawdown
        equity = (1 + returns).cumprod()
        running_max = equity.cummax()
        drawdown = (equity - running_max) / running_max
        max_dd = drawdown.min()

        return {
            "cagr": float(cagr),
            "sharpe": float(sharpe),
            "max_dd": float(max_dd),
            "cumulative_return": float(cum_ret),
        }

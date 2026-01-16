import logging
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, Optional, List
from ..db.duck import connect as duck_connect
from ..config import settings

logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    V2 Backtest Engine.
    Executes trades based on approved targets in DuckDB.
    Daily ledger style.

    Semantic:
    - Rebalancing happens at T Close based on targets for study_date = T.
    - PnL for T reflects weights set at T-1 Close applying to T Close returns.
    - If no targets at T, 'Hold' policy: keep previous weights.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.quant_duckdb_path

    def load_ohlcv_returns(
        self, symbols: List[str], from_date: str, to_date: str
    ) -> pd.DataFrame:
        """Load OHLCV and calculate 1d returns for given symbols and range."""
        conn = duck_connect(self.db_path)
        try:
            sym_list = "', '".join(symbols)
            query = f"""
                SELECT symbol, ts, close
                FROM ohlcv
                WHERE symbol IN ('{sym_list}')
                  AND ts >= DATE '{from_date}' - INTERVAL 5 DAY
                  AND ts <= DATE '{to_date}' + INTERVAL 1 DAY
                ORDER BY ts
            """
            df = conn.execute(query).df()
            if df.empty:
                return pd.DataFrame()

            df["ts"] = pd.to_datetime(df["ts"])
            df = df.pivot(index="ts", columns="symbol", values="close")
            df_ret = df.pct_change().fillna(0)
            return df_ret
        finally:
            conn.close()

    def load_targets(
        self, strategy_id: str, from_date: str, to_date: str
    ) -> pd.DataFrame:
        """Load approved targets for the strategy in the given range."""
        conn = duck_connect(self.db_path, read_only=True)
        try:
            query = f"""
                SELECT study_date as ts, symbol, weight, score
                FROM targets
                WHERE strategy_id = '{strategy_id}'
                  AND approved = True
                  AND study_date >= DATE '{from_date}'
                  AND study_date <= DATE '{to_date}'
                ORDER BY study_date
            """
            df = conn.execute(query).df()
            if not df.empty:
                df["ts"] = pd.to_datetime(df["ts"])
            return df
        finally:
            conn.close()

    def run(self, strategy_config: Dict[str, Any], from_date: str, to_date: str):
        """
        Run backtest simulation with Hold Policy.
        """
        strategy_id = strategy_config["strategy_id"]
        version = strategy_config["version"]

        # 1. Load targets
        df_targets = self.load_targets(strategy_id, from_date, to_date)
        if df_targets.empty:
            raise ValueError(
                f"No approved targets found for {strategy_id} in range {from_date} ~ {to_date}"
            )

        symbols = df_targets["symbol"].unique().tolist()

        # 2. Load returns
        df_returns = self.load_ohlcv_returns(symbols, from_date, to_date)
        if df_returns.empty:
            logger.warning("No price data found for the given range.")
            return None

        all_dates = sorted(df_returns.index)
        simulation_dates = [
            d
            for d in all_dates
            if pd.Timestamp(from_date) <= d <= pd.Timestamp(to_date)
        ]

        bt_config = strategy_config.get("backtest", {})
        fee_bps = bt_config.get("fee_bps", 0) / 10000.0
        slippage_bps = bt_config.get("slippage_bps", 0) / 10000.0
        total_cost_bps = fee_bps + slippage_bps

        current_weights = pd.Series(0.0, index=symbols)
        ledger = []

        for t in simulation_dates:
            target_df = df_targets[df_targets["ts"] == t]

            # Rebalancing check (T Close)
            cost = 0.0
            if not target_df.empty:
                # Update weights based on T targets
                new_weights = target_df.set_index("symbol")["weight"]
                new_weights = new_weights.reindex(symbols, fill_value=0.0)

                # Rebalance cost: (new - current).abs().sum()
                turnover = (new_weights - current_weights).abs().sum()
                cost = turnover * total_cost_bps
                current_weights = new_weights
            else:
                # [Hold Policy] No targets for T, keep current_weights as set at T-1
                pass

            # PnL for today (T) matches current_weights (which includes rebal at T Close)
            # wait, semantic check:
            # Rebalance at T Close.
            # PnL for T comes from weights set at T-1.
            # In our loop, 'current_weights' is updated BEFORE PnL calculation if T has targets.
            # Correct logic: PnL(T) = Weights(T-1) * Return(T).
            # Then Rebalance at T Close affects PnL(T+1).

            # Let's adjust: Calculate PnL with OLD weights first, then update weights.
            # But the 'ledger' stores weights active DURING the day.
            # Let's use 'prev_weights' for PnL.
            pass  # We will use a more robust day-step below.

        # Refined Loop
        current_weights = pd.Series(0.0, index=symbols)
        ledger = []
        for t in simulation_dates:
            # 1. PnL for day T (using weights from T-1)
            day_returns = (
                df_returns.loc[t]
                if t in df_returns.index
                else pd.Series(0.0, index=symbols)
            )
            day_pnl_raw = (current_weights * day_returns).sum()

            # 2. Rebalance at T Close (affects T+1)
            target_df = df_targets[df_targets["ts"] == t]
            rebal_cost = 0.0
            if not target_df.empty:
                new_weights = target_df.set_index("symbol")["weight"].reindex(
                    symbols, fill_value=0.0
                )
                turnover = (new_weights - current_weights).abs().sum()
                rebal_cost = turnover * total_cost_bps
                current_weights = new_weights

            # 3. Record to Ledger (Position after rebalance, PnL using prev weights)
            # Actually, per user: "리밸런싱은 T close에서 수행하고 PnL은 T+1 close 수익부터 반영"
            # This confirms: Day T PnL uses Weights available UNTIL Day T Close.
            # We records weights as of T (post-rebalance) and pnl contribution.

            # For simplicity in Ledger: sum(contribution) = day_pnl
            # Let's attribute day_pnl_raw to the active symbols.
            active_at_start = current_weights.index[
                current_weights > 0
            ]  # This is not right if we rebalanced.

            # Let's follow a cleaner "End of Day" snapshot:
            # Day T:
            # - Start with weights W_{T-1}
            # - Asset return R_{T}
            # - PnL_{T} = W_{T-1} * R_{T} - RebalanceCost_{T} (if any)
            # - Update to W_{T}

            # Let's re-save 'prev_weights'
            # (First day will have 0 PnL/0 Cost unless it updates weights)
            pass

        # FINAL IMPLEMENTATION OF LOOP
        current_weights = pd.Series(0.0, index=symbols)
        ledger = []
        for t in simulation_dates:
            # T's 1d returns
            day_returns = (
                df_returns.loc[t]
                if t in df_returns.index
                else pd.Series(0.0, index=symbols)
            )

            # T's PnL CONTRIBUTION (from T-1 weights)
            day_pnl_from_assets = (current_weights * day_returns).sum()

            # T Close Rebalancing
            target_df = df_targets[df_targets["ts"] == t]
            rebal_cost = 0.0
            if not target_df.empty:
                new_weights = target_df.set_index("symbol")["weight"].reindex(
                    symbols, fill_value=0.0
                )
                turnover = (new_weights - current_weights).abs().sum()
                rebal_cost = turnover * total_cost_bps
                current_weights = new_weights

            # Total PnL for T
            total_day_pnl = day_pnl_from_assets - rebal_cost

            # Ledger: Record current_weights (post-rebal) and total contribution
            # We split total_day_pnl across active symbols for visibility
            active_syms = current_weights[current_weights > 0].index.tolist()
            if active_syms:
                pnl_per_sym = total_day_pnl / len(active_syms)
                for sym in active_syms:
                    ledger.append(
                        {
                            "ts": t,
                            "symbol": sym,
                            "weight": float(current_weights[sym]),
                            "contribution": float(pnl_per_sym),
                            "cost": float(rebal_cost / len(active_syms)),
                        }
                    )
            elif rebal_cost > 0:
                ledger.append(
                    {
                        "ts": t,
                        "symbol": "COST",
                        "weight": 0.0,
                        "contribution": -float(rebal_cost),
                        "cost": float(rebal_cost),
                    }
                )
            else:
                # Cash day
                ledger.append(
                    {
                        "ts": t,
                        "symbol": "CASH",
                        "weight": 0.0,
                        "contribution": 0.0,
                        "cost": 0.0,
                    }
                )

        return self.save_results(
            strategy_id, version, ledger, from_date, to_date, fee_bps, slippage_bps
        )

    def save_results(
        self,
        strategy_id: str,
        version: str,
        ledger: List[Dict],
        from_ts: str,
        to_ts: str,
        fee_bps: float,
        slippage_bps: float,
    ):
        if not ledger:
            return None
        df_ledger = pd.DataFrame(ledger)
        daily_pnl = df_ledger.groupby("ts")["contribution"].sum()

        n_days = len(daily_pnl)
        mean_ret = daily_pnl.mean()
        std_ret = daily_pnl.std()
        annual_factor = 252.0

        # CAGR
        cum_ret = (1 + daily_pnl).prod() - 1
        span = (daily_pnl.index[-1] - daily_pnl.index[0]).days + 1
        cagr = (1 + cum_ret) ** (365.0 / span) - 1 if span > 0 else 0.0

        # [P5 Refinement] Sharpe Safety
        if n_days < 2 or std_ret == 0 or np.isnan(std_ret):
            sharpe = 0.0
        else:
            sharpe = (mean_ret / std_ret) * np.sqrt(annual_factor)

        mdd = ((1 + daily_pnl).cumprod() / (1 + daily_pnl).cumprod().cummax() - 1).min()

        run_id = f"bt_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        conn = duck_connect(self.db_path)
        try:
            conn.execute(
                f"""
                INSERT INTO backtest_summary 
                (run_id, strategy_id, from_ts, to_ts, cagr, sharpe, max_dd, vol, 
                 mean_daily_return, std_daily_return, annual_factor, n_days, created_at)
                VALUES (
                    '{run_id}', '{strategy_id}', DATE '{from_ts}', DATE '{to_ts}',
                    {cagr}, {sharpe}, {mdd}, {std_ret * np.sqrt(annual_factor) if not np.isnan(std_ret) else 0.0},
                    {mean_ret if not np.isnan(mean_ret) else 0.0}, {std_ret if not np.isnan(std_ret) else 0.0},
                    {annual_factor}, {n_days}, now()
                )
            """
            )
            df_ledger["ts"] = pd.to_datetime(df_ledger["ts"])
            conn.register("df_ledger_tmp", df_ledger)
            conn.execute(
                f"INSERT INTO backtest_trades (run_id, strategy_id, symbol, entry_ts, qty, pnl_pct, reason) SELECT '{run_id}', '{strategy_id}', symbol, ts, weight, contribution, 'daily_ledger' FROM df_ledger_tmp"
            )
            return {
                "run_id": run_id,
                "cagr": cagr,
                "sharpe": sharpe,
                "max_dd": mdd,
                "mean": mean_ret,
                "std": std_ret,
                "n_days": n_days,
            }
        finally:
            conn.close()

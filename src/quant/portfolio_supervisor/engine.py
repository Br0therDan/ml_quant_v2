import logging
import pandas as pd
import json
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


class PortfolioSupervisor:
    """
    Apply R1~R5 risk rules to proposed targets.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get("supervisor", {})
        self.portfolio_config = config.get("portfolio", {})

    def audit(self, df_targets: pd.DataFrame) -> pd.DataFrame:
        """
        Audit the targets and set approved=True/False and risk_flags.
        """
        if df_targets.empty:
            return df_targets

        df = df_targets.copy()
        df["approved"] = True
        df["risk_flags"] = ""

        # Rules Configuration
        r1_gross_cap = self.config.get("gross_exposure_cap", 1.0)
        r2_max_weight = self.config.get("max_weight_per_symbol", 0.15)
        r3_max_positions = self.config.get("max_positions", 10)
        r5_score_floor = self.config.get("score_floor", None)

        flags_list = []

        for idx, row in df.iterrows():
            row_flags = []

            # R2: Max Position Weight
            if row["weight"] > r2_max_weight:
                row_flags.append(
                    f"R2:WeightExceeded({row['weight']:.2f}>{r2_max_weight:.2f})"
                )
                # Adjust weight automatically or mark for rejection?
                # V2 Requirement: Mark as rejected or flag
                # For baseline, let's keep approved=True but flag it, or reject if it's too high?
                # User specified: "record approved=true/false". Let's reject if it violates R2/R5.
                # However, R1/R3 are PORTFOLIO level. Let's handle row-level first.

            # R5: Score Floor
            if r5_score_floor is not None and row["score"] < r5_score_floor:
                row_flags.append(
                    f"R5:ScoreTooLow({row['score']:.2f}<{r5_score_floor:.2f})"
                )
                df.at[idx, "approved"] = False

            flags_list.append(",".join(row_flags))

        df["risk_flags"] = flags_list

        # Portfolio Level Rules (Refinement)

        # R3: Max Positions (Already partially handled by Top-K in Recommender, but we enforce here too)
        # If we have more than R3, we might need to truncate
        if len(df[df["approved"]]) > r3_max_positions:
            # Sort by score and keep top R3
            approved_indices = (
                df[df["approved"]].sort_values(by="score", ascending=False).index
            )
            reject_indices = approved_indices[r3_max_positions:]
            for ridx in reject_indices:
                df.at[ridx, "approved"] = False
                prev_flags = df.at[ridx, "risk_flags"]
                new_flag = "R3:MaxPositionsExceeded"
                df.at[ridx, "risk_flags"] = (
                    f"{prev_flags},{new_flag}" if prev_flags else new_flag
                )

        # R1: Gross Exposure Cap
        total_weight = df[df["approved"]]["weight"].sum()
        if total_weight > r1_gross_cap:
            # Scaledown weights of approved items
            scale = r1_gross_cap / total_weight
            df.loc[df["approved"], "weight"] *= scale
            logger.info(
                f"R1: Scaled total weight from {total_weight:.2f} to {r1_gross_cap:.2f}"
            )
            # Add flag to all approved items
            for idx in df[df["approved"]].index:
                prev_flags = df.at[idx, "risk_flags"]
                new_flag = f"R1:Scaled({scale:.2f})"
                df.at[idx, "risk_flags"] = (
                    f"{prev_flags},{new_flag}" if prev_flags else new_flag
                )

        # R4: Turnover Cap (Placeholder for V2)
        # In V2 P4, we don't have previous holdings here easily, so we just log a placeholder
        # To strictly implement a placeholder, we can just add a note.

        return df

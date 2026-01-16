import pandas as pd
from typing import List, Tuple


def get_time_series_splits(
    dates: pd.DatetimeIndex,
    n_splits: int = 5,
    train_size: int = 252,  # 1 year of trading days
    test_size: int = 60,  # target horizon
    gap: int = 60,  # purge gap to prevent leakage (set to horizon)
) -> List[Tuple[pd.DatetimeIndex, pd.DatetimeIndex]]:
    """
    Time-series Walk-forward splits.
    Returns list of (train_idx, test_idx)
    """
    splits = []
    dates = dates.sort_values()
    n_samples = len(dates)

    # Start from the end and move backwards
    end_idx = n_samples
    for _ in range(n_splits):
        test_end = end_idx
        test_start = test_end - test_size

        if test_start < 0:
            break

        train_end = test_start - gap
        train_start = train_end - train_size

        if train_start < 0:
            break

        train_dates = dates[train_start:train_end]
        test_dates = dates[test_start:test_end]

        splits.append((train_dates, test_dates))

        # Move back by test_size for next split
        end_idx -= test_size

    return splits[::-1]  # Return in chronological order

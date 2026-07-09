import pandas as pd
import pytest


@pytest.fixture
def snapshots() -> pd.DatetimeIndex:
    """Two days of hourly snapshots."""
    return pd.date_range("2026-01-01", periods=48, freq="h")

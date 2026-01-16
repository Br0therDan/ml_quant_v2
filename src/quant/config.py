from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    alpha_vantage_api_key: str | None = "M9TJCCBXW5PJZ3HF"

    quant_data_dir: Path = Path("./data")
    quant_duckdb_path: Path = Path("./data/quant.duckdb")
    quant_sqlite_path: Path = Path("./data/meta.db")

    # Execution artifacts SSOT
    quant_artifacts_dir: Path = Path("./artifacts")
    quant_runs_dir: Path = Path("./artifacts/runs")

    quant_log_level: str = "INFO"


settings = Settings()

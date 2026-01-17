from __future__ import annotations

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # API Key: System environment variables or .env file take precedence.
    alpha_vantage_api_key: str | None = None

    quant_data_dir: Path = Path("./data")
    quant_duckdb_path: Path = Path("./data/quant.duckdb")
    quant_sqlite_path: Path = Path("./data/meta.db")

    # Execution artifacts SSOT
    quant_artifacts_dir: Path = Path("./artifacts")
    quant_runs_dir: Path = Path("./artifacts/runs")

    quant_log_level: str = "INFO"

    @model_validator(mode="after")
    def _fallback_to_streamlit_secrets(self) -> Settings:
        """
        Fallback to Streamlit Secrets if API Key is not found in env/dotenv.
        Supports local .streamlit/secrets.toml and Streamlit Cloud Secrets.
        """
        if not self.alpha_vantage_api_key:
            try:
                import streamlit as st

                # Check if we are running in a context where st.secrets is available
                val = st.secrets.get("ALPHA_VANTAGE_API_KEY")
                if val:
                    self.alpha_vantage_api_key = val
            except Exception:
                # Silently ignore if streamlit is not present or secrets not found
                pass
        return self

    @property
    def project_root(self) -> Path:
        """Determines project root based on data directory."""
        return self.quant_data_dir.parent


settings = Settings()

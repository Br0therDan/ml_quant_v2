from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel, create_engine, Session, select


class Symbol(SQLModel, table=True):
    __tablename__ = "symbols"

    symbol: str = Field(primary_key=True)
    name: Optional[str] = None
    sector: Optional[str] = None
    currency: Optional[str] = Field(default="USD")
    is_active: int = Field(default=1)  # 1/0
    priority: int = Field(default=0)


class Experiment(SQLModel, table=True):
    __tablename__ = "experiments"

    experiment_id: str = Field(primary_key=True)
    name: str
    description: Optional[str] = None
    feature_set_id: Optional[str] = None
    label_set_id: Optional[str] = None
    split_policy_json: Optional[str] = None
    params_json: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class Model(SQLModel, table=True):
    __tablename__ = "models"

    model_id: str = Field(primary_key=True)
    experiment_id: Optional[str] = None
    algo: Optional[str] = None
    params_json: Optional[str] = None
    train_range: Optional[str] = None
    feature_version: Optional[str] = None
    label_version: Optional[str] = None
    metrics_json: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class Run(SQLModel, table=True):
    __tablename__ = "runs"

    run_id: str = Field(primary_key=True)
    kind: str  # ingest, features, labels, train, score, recommend, backtest
    status: str  # running, success, fail
    started_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    ended_at: Optional[str] = None
    config_json: Optional[str] = None
    error_text: Optional[str] = None

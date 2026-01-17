from datetime import datetime

from sqlmodel import Field, SQLModel


class Symbol(SQLModel, table=True):
    __tablename__ = "symbols"

    symbol: str = Field(primary_key=True)
    name: str | None = None
    sector: str | None = None
    currency: str | None = Field(default="USD")
    is_active: int = Field(default=1)  # 1/0
    priority: int = Field(default=0)


class Experiment(SQLModel, table=True):
    __tablename__ = "experiments"

    experiment_id: str = Field(primary_key=True)
    name: str
    description: str | None = None
    feature_set_id: str | None = None
    label_set_id: str | None = None
    split_policy_json: str | None = None
    params_json: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class Model(SQLModel, table=True):
    __tablename__ = "models"

    model_id: str = Field(primary_key=True)
    experiment_id: str | None = None
    algo: str | None = None
    params_json: str | None = None
    train_range: str | None = None
    feature_version: str | None = None
    label_version: str | None = None
    metrics_json: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class Run(SQLModel, table=True):
    __tablename__ = "runs"

    run_id: str = Field(primary_key=True)
    kind: str  # ingest, features, labels, train, score, recommend, backtest
    status: str  # running, success, fail
    started_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    ended_at: str | None = None
    config_json: str | None = None
    error_text: str | None = None

-- DuckDB schema: time-series facts

CREATE TABLE IF NOT EXISTS ohlcv (
  symbol TEXT NOT NULL,
  ts DATE NOT NULL,
  open DOUBLE,
  high DOUBLE,
  low DOUBLE,
  close DOUBLE,
  volume DOUBLE,
  adjusted_close DOUBLE,
  source TEXT,
  ingested_at TIMESTAMP,
  PRIMARY KEY(symbol, ts)
);

CREATE TABLE IF NOT EXISTS returns (
  symbol TEXT NOT NULL,
  ts DATE NOT NULL,
  ret_1d DOUBLE,
  ret_5d DOUBLE,
  ret_20d DOUBLE,
  ret_60d DOUBLE,
  PRIMARY KEY(symbol, ts)
);

CREATE TABLE IF NOT EXISTS features_daily (
  symbol TEXT NOT NULL,
  ts DATE NOT NULL,
  feature_name TEXT NOT NULL,
  feature_value DOUBLE,
  feature_version TEXT NOT NULL,
  computed_at TIMESTAMP,
  PRIMARY KEY(symbol, ts, feature_name, feature_version)
);

CREATE TABLE IF NOT EXISTS labels (
  symbol TEXT NOT NULL,
  ts DATE NOT NULL,
  label_name TEXT NOT NULL,
  label_value DOUBLE,
  label_version TEXT NOT NULL,
  PRIMARY KEY(symbol, ts, label_name, label_version)
);

CREATE TABLE IF NOT EXISTS predictions (
  symbol TEXT NOT NULL,
  ts DATE NOT NULL,
  model_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  score DOUBLE,
  calibrated_score DOUBLE,
  generated_at TIMESTAMP,
  PRIMARY KEY(symbol, ts, model_id, task_id)
);

CREATE TABLE IF NOT EXISTS targets (
  strategy_id TEXT NOT NULL,
  version TEXT NOT NULL,
  study_date DATE NOT NULL,
  symbol TEXT NOT NULL,
  weight DOUBLE,
  score DOUBLE,
  approved BOOLEAN,
  risk_flags TEXT,
  reason TEXT,
  generated_at TIMESTAMP,
  PRIMARY KEY(strategy_id, study_date, symbol)
);

CREATE TABLE IF NOT EXISTS backtest_trades (
  run_id TEXT NOT NULL,
  strategy_id TEXT,
  symbol TEXT NOT NULL,
  entry_ts DATE,
  entry_price DOUBLE,
  qty DOUBLE,
  exit_ts DATE,
  exit_price DOUBLE,
  pnl DOUBLE,
  pnl_pct DOUBLE,
  fees DOUBLE,
  slippage_est DOUBLE,
  reason TEXT
);

CREATE TABLE IF NOT EXISTS backtest_summary (
  run_id TEXT NOT NULL,
  strategy_id TEXT,
  from_ts DATE,
  to_ts DATE,
  cagr DOUBLE,
  sharpe DOUBLE,
  max_dd DOUBLE,
  vol DOUBLE,
  mean_daily_return DOUBLE,
  std_daily_return DOUBLE,
  annual_factor DOUBLE,
  turnover DOUBLE,
  win_rate DOUBLE,
  avg_trade DOUBLE,
  num_trades BIGINT,
  n_days BIGINT,
  fee_bps DOUBLE,
  slippage_bps DOUBLE,
  created_at TIMESTAMP,
  PRIMARY KEY(run_id)
);

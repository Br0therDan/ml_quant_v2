# DB_SCHEMA.md (V2)
- Version: v2.0.0
- Created: 2026-01-15
- Last Updated: 2026-01-15

> V2의 데이터 계약(Contracts)을 구체 스키마로 정의한다.  
> **DuckDB = 시계열/산출물**, **SQLite = 메타데이터(SQLModel)** 를 원칙으로 한다.

---

## 1. DuckDB Schema (Time-series & Artifacts)

### 1.1 `ohlcv` (SSOT, Fact)
- PK: `(symbol, ts)`
- 목적: 원천 가격/거래량 사실 데이터

| Column | Type | Note |
|---|---|---|
| symbol | TEXT | ticker |
| ts | DATE | trading day |
| open | DOUBLE |  |
| high | DOUBLE |  |
| low | DOUBLE |  |
| close | DOUBLE |  |
| volume | DOUBLE |  |
| adjusted_close | DOUBLE | nullable |
| source | TEXT | ex) alpha_vantage |
| ingested_at | TIMESTAMP | ingestion time |

---

### 1.2 `returns` (Optional)
- PK: `(symbol, ts)`
- 목적: 수익률 파생(피처/라벨 생성에 활용)

| Column | Type |
|---|---|
| symbol | TEXT |
| ts | DATE |
| ret_1d | DOUBLE |
| ret_5d | DOUBLE |
| ret_20d | DOUBLE |
| ret_60d | DOUBLE |

---

### 1.3 `features_daily` (Long-form Feature Store)
- PK: `(symbol, ts, feature_name, feature_version)`
- 목적: 버저닝된 피처 저장

| Column | Type | Note |
|---|---|---|
| symbol | TEXT |  |
| ts | DATE |  |
| feature_name | TEXT |  |
| feature_value | DOUBLE |  |
| feature_version | TEXT | ex) v1 |
| computed_at | TIMESTAMP |  |

---

### 1.4 `labels` (Long-form Label Store)
- PK: `(symbol, ts, label_name, label_version)`

| Column | Type | Note |
|---|---|---|
| symbol | TEXT |  |
| ts | DATE |  |
| label_name | TEXT | ex) fwd_ret_60d |
| label_value | DOUBLE |  |
| label_version | TEXT | ex) v1 |

---

### 1.5 `predictions`
- PK: `(symbol, ts, model_id, task_id)`

| Column | Type | Note |
|---|---|---|
| symbol | TEXT |  |
| ts | DATE |  |
| model_id | TEXT | registry key |
| task_id | TEXT | bull/bear |
| score | DOUBLE | model output |
| calibrated_score | DOUBLE | nullable |
| generated_at | TIMESTAMP |  |

---

### 1.6 `targets` (Strategy Outputs)
- PK(권장): `(strategy_id, asof, symbol)`
- 목적: 추천 포지션(승인 전/후 동일 테이블에 저장 가능)

| Column | Type | Note |
|---|---|---|
| strategy_id | TEXT | YAML id |
| version | TEXT | YAML version |
| asof | DATE | rebalance date |
| symbol | TEXT |  |
| weight | DOUBLE | target weight |
| score | DOUBLE | optional |
| approved | BOOLEAN | supervisor result |
| risk_flags | TEXT | JSON string or comma list |
| reason | TEXT | short rationale |
| generated_at | TIMESTAMP |  |

---

### 1.7 `backtest_trades`
- 목적: 거래 단위 로그(최소 스키마)

| Column | Type |
|---|---|
| run_id | TEXT |
| strategy_id | TEXT |
| symbol | TEXT |
| entry_ts | DATE |
| entry_price | DOUBLE |
| qty | DOUBLE |
| exit_ts | DATE |
| exit_price | DOUBLE |
| pnl | DOUBLE |
| pnl_pct | DOUBLE |
| fees | DOUBLE |
| slippage_est | DOUBLE |
| reason | TEXT |

---

### 1.8 `backtest_summary`
- 목적: run 단위 요약 성과

| Column | Type |
|---|---|
| run_id | TEXT |
| strategy_id | TEXT |
| from_ts | DATE |
| to_ts | DATE |
| cagr | DOUBLE |
| sharpe | DOUBLE |
| max_dd | DOUBLE |
| vol | DOUBLE |
| turnover | DOUBLE |
| win_rate | DOUBLE |
| avg_trade | DOUBLE |
| num_trades | BIGINT |
| fee_bps | DOUBLE |
| slippage_bps | DOUBLE |
| created_at | TIMESTAMP |

---

## 2. SQLite Schema (Meta DB, SQLModel)

> SQLite는 SQLModel 기반으로 관리한다.  
> V2에서는 Alembic 마이그레이션을 강제하지 않으며, 초기 단계에서는 drop/recreate를 허용한다.

### 2.1 `symbols`
| Column | Type | Note |
|---|---|---|
| symbol | TEXT (PK) | ticker |
| name | TEXT | optional |
| sector | TEXT | optional |
| currency | TEXT | optional |
| is_active | INTEGER | 1/0 |
| priority | INTEGER | ordering |

---

### 2.2 `experiments`
| Column | Type |
|---|---|
| experiment_id | TEXT (PK) |
| name | TEXT |
| description | TEXT |
| feature_set_id | TEXT |
| label_set_id | TEXT |
| split_policy_json | TEXT |
| params_json | TEXT |
| created_at | TEXT |

---

### 2.3 `models`
| Column | Type |
|---|---|
| model_id | TEXT (PK) |
| experiment_id | TEXT |
| algo | TEXT |
| params_json | TEXT |
| train_range | TEXT |
| feature_version | TEXT |
| label_version | TEXT |
| metrics_json | TEXT |
| created_at | TEXT |

---

### 2.4 `runs`
| Column | Type |
|---|---|
| run_id | TEXT (PK) |
| kind | TEXT |
| status | TEXT |
| started_at | TEXT |
| ended_at | TEXT |
| config_json | TEXT |
| error_text | TEXT |

---

## 3. Strategy YAML Schema (V2 Minimal)

> YAML은 “전략 조립 설정”만 담당한다. 로직/수식/조건식을 YAML로 확장하지 않는다.

### 3.1 Minimal Fields
- `strategy_id`: 전역 고유
- `version`: 전략 버전
- `universe`: 심볼 선택 정의
- `signal`: 신호/모델/랭킹 선택
- `rebalance`: 주기/룰
- `portfolio`: Top-K, sizing
- `supervisor`: 경량 규제(R1~R5)
- `execution`: 체결 가정(실거래 아님)
- `backtest`: 비용/기간 등

### 3.2 Supervisor Rules Parameters (Recommended)
- R1: `gross_exposure_cap` (default 1.0)
- R2: `max_weight_per_symbol` (default 0.15)
- R3: `max_positions` (default 10)
- R4: `turnover_cap` (default 0.30)
- R5: `score_floor` 또는 `top_k` (default top_k)

---

## 4. Change Log
- v2.0.0 (2026-01-15)
  - Initial schema contract for V2

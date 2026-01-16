# V2 Phase P5 Refinement Plan: Backtest Engine & Data Pipeline

버전: v1.1.0
작성일: 2026-01-15

## Executive Summary
Phase P5의 백테스트 엔진을 보다 견고하게 보완한다. 데이터가 없는 기간에 대한 대응(Hold 정책), 상세 성과 지표 저장, 그리고 기술적 부채인 SQLAlchemy 의존성을 제거하여 DuckDB Python API 기반의 순수 SQL 환경으로 통합한다.

## Objective
- **Backtest Robustness**: 추천 데이터(`targets`)가 없는 날짜에 대해 직전 비중 유지(Hold) 로직 강화. 전체 기간 데이터 부재 시 실패 처리.
- **Detailed Metrics**: `backtest_summary`에 Sharpe 계산 기초 통계량(`mean`, `std`, `n_days` 등) 추가 저장. (NaN/inf 방지 예외 처리 포함)
- **Dependency Cleanup**: `sqlalchemy`, `duckdb-engine` 의존성 제거 및 Raw SQL로 전면 전환.
- **Migration Policy**: 기존 DB 보존을 위해 1회성 마이그레이션 쿼리 제공 및 `schema_duck.sql` 업데이트.

## Proposed Changes

### 1. Database Schema (`src/quant/db/schema_duck.sql`)
- [ ] `backtest_summary` 테이블 컬럼 추가:
    - `mean_daily_return` (DOUBLE)
    - `std_daily_return` (DOUBLE)
    - `annual_factor` (DOUBLE)
    - `n_days` (BIGINT)
- [ ] `RUNBOOK.md`에 기존 DB용 `ALTER TABLE` 마이그레이션 가이드 추가.

### 2. Backtest Engine (`src/quant/backtest_engine/engine.py`)
- [ ] `run` 메소드 보완:
    - 시작 시 `targets` 로드 후 비어있으면 `ValueError` 발생.
    - **T close 리밸런싱 / T+1 PnL 반영**: T일 targets 기반 가중치가 T+1일 수익률에 적용됨을 코드와 주석으로 명시.
    - 시뮬레이션 중 `targets`가 없는 날은 `current_weights`를 변경하지 않고 유지(Hold).
- [ ] `save_results` 메소드 보완:
    - `daily_returns` 기반으로 `mean`, `std`, `n_days` 계산.
    - **Sharpe 예외 처리**: `n_days < 2` 또는 `std == 0`이면 `sharpe`를 0.0으로 처리.
    - `INSERT` SQL 문에 신규 컬럼 반영.

### 3. CLI Integration (`src/quant/cli.py`)
- [ ] `save_targets` 함수 수정:
    - `sqlalchemy`와 `create_engine` 제거.
    - `src.quant.db.duck.connect`와 Raw SQL(`INSERT INTO ... SELECT`) 사용.
- [ ] `recommend`, `backtest` 커맨드 내 불필요한 import 정리.

## Verification Plan

### Automated Tests & Verification
1.  **Dependency Check**: `grep -r "sqlalchemy" src/quant` 수행 시 `src/quant/repos/` 외(SQLite용)에는 없어야 함.
2.  **Backtest Execution**: 
    - `strategies/example.yaml` 실행 후 성공 확인.
    - 시작일/종료일을 넓게 잡아 중간에 targets가 없는 경우에도 'Hold' 로직으로 완주하는지 확인.
3.  **DB Verification Query**:
    ```sql
    SELECT run_id, cagr, sharpe, mean_daily_return, std_daily_return, n_days 
    FROM backtest_summary 
    ORDER BY created_at DESC LIMIT 1;
    ```

### Manual Verification
- `uv run quant backtest` 실행 시 `Sharpe Ratio`가 0 이상으로 나오는지, 통계량이 정합성 있게 저장되는지 확인.

# V2 Phase P5 Implementation Plan: Backtest Engine v1

버전: v1.0.0
작성일: 2026-01-15

## Executive Summary
Phase P5에서는 Phase P4에서 생성된 `targets`(추천) 데이터를 바탕으로 과거 수익률을 시뮬레이션하는 백테스트 엔진을 구축한다. Daily Close 기준으로 체결을 가정하며, 거래 비용(수수료, 슬리피지)을 반영하여 최종 성과 지표를 DuckDB에 적재한다.

## Objective
- DuckDB `targets` (approved=true) 기반의 리밸런싱 시맨틱 구현
- Daily Close 체결 및 비용(fee_bps, slippage_bps) 반영 로직
- DuckDB `backtest_trades`, `backtest_summary` 적재
- `quant backtest` CLI 커맨드 및 Run Registry 연동
- 미래 확장을 위한 `model_score` 신호 입력 Hook 추가 (YAML 스키마)

## Progress Dashboard
| Phase | Task | Status | Note |
|---|---|---|---|
| P5.1 | Backtest Engine 핵심 로직 구현 | [ ] | Targets 기반 시뮬레이터 |
| P5.2 | 성과 지표 산출 및 DB 적재 | [ ] | Summary & Trades |
| P5.3 | CLI & Run Registry 연동 | [ ] | backtest 커맨드 |
| P5.4 | YAML Schema 확장 (Hook) | [ ] | model_score 지원 준비 |
| P5.5 | 동작 검증 및 Snapshot | [ ] | 최종 검증 |

## Implementation Plan

### 1. Backtest Engine 구현 (`src/quant/backtest_engine/engine.py`)
- [ ] 입력: `strategy_id`, `from_ts`, `to_ts`
- [ ] 데이터 로드:
    - DuckDB `targets`에서 `approved=true`인 비중 로드
    - DuckDB `ohlcv`에서 수익률(`ret_1d`) 계산용 종가 로드
- [ ] 시뮬레이션 로직 (**사용자 지침 반영**):
    - **T close 리밸런싱**: T일 targets 기반으로 비중 결정.
    - **T+1 PnL 반영**: T일 결정된 비중이 T+1일 수익률에 적용되도록 고정.
    - **Daily Ledger 방식**: 개별 진입/청산 이벤트가 아닌 일별 포지션 변화, 비용, 기여도를 `backtest_trades`에 기록.
    - 거래 비용: `abs(new_weight - old_weight) * (fee + slippage)`

### 2. DB 적재 및 CLI 연동 (`src/quant/cli.py`)
- [ ] **Raw SQL 사용**: DuckDB 적재 시 SQLAlchemy/duckdb-engine을 사용하지 않고 `duckdb` python API와 Raw SQL로만 구현.
- [ ] `quant backtest` 커맨드 구현
    - `--strategy`, `--from`, `--to` 인자 지원
    - `RunRegistry.run_start(kind="backtest")` 연동

### 3. 미래 확장 Hook (`src/quant/strategy_lab/loader.py`)
- [ ] YAML `signal.type`에 `model_score` 추가 허용
- [ ] `inputs.model_id`, `inputs.task_id` 필드 파싱 지원 (Optional)

### 4. 운영 규칙 업데이트 (`docs/implementation/v2/RUNBOOK.md`)
- [ ] 백테스트 실행 절차 및 확인 쿼리 예시 보완

## Verification Plan
### Automated Tests & 쿼리
- `strategies/example.yaml` 기반 백테스트 실행:
    - `uv run quant backtest --strategy strategies/example.yaml --from 2024-01-01 --to 2025-12-31`
- DuckDB 검증 쿼리:
    ```sql
    -- 요약 결과 확인
    SELECT * FROM backtest_summary ORDER BY created_at DESC LIMIT 5;
    -- 상세 거래 확인
    SELECT count(*) FROM backtest_trades;
    ```
- SQLite `runs` 확인: `kind='backtest'`, `status='success'`.

### Manual Verification
- Targets 데이터가 없는 기간에 대해 실행 시 적절한 경고 출력 여부 확인.
- 비용 설정(fee_bps) 변경 시 성과 지차 확인.

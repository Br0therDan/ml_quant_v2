# V2 Phase P3 Implementation Plan: Feature Store (Features/Labels)

버전: v1.0.0
작성일: 2026-01-15

## Executive Summary
Phase P3에서는 자산 가격(OHLCV) 데이터를 바탕으로 모델 학습 및 분석에 필요한 피처(Features)와 레이블(Labels)을 생성하고, 이를 DuckDB의 long-form 저장소에 버저닝하여 관리하는 시스템을 구축한다.

## Objective
- DuckDB `features_daily` 테이블에 v1 피처 세트 적재
- DuckDB `labels` 테이블에 v1 레이블 세트 적재
- Quality Gate를 통한 데이터 무결성 확보 (NaN 제거 등)
- CLI 커맨드(`quant features`, `quant labels`) 및 Run Registry 연동

## Progress Dashboard
| Phase | Task | Status | Note |
|---|---|---|---|
| P3.1 | Feature Calculator 구현 | [ ] | v1 피처 세트 계산 로직 |
| P3.2 | Label Calculator 구현 | [ ] | v1 레이블 세트 계산 로직 |
| P3.3 | CLI & Run Registry 연동 | [ ] | features, labels 커맨드 |
| P3.4 | 동작 검증 및 Snapshot | [ ] | 최종 검증 |

## Implementation Plan

### 1. Feature Store 구현 (`src/quant/feature_store/features.py`)
- [ ] DuckDB에서 `ohlcv` 데이터를 Pandas DataFrame으로 로드
- [ ] v1 피처 계산 로직 구현:
    - `ret_1d`, `ret_5d`, `ret_20d`, `ret_60d`
    - `vol_20d`: `ret_1d`의 rolling standard deviation
    - `gap_open`: `(open - prev_close) / prev_close`
    - `hl_range`: `(high - low) / close`
    - `volume_ratio_20d`: `volume / volume.rolling(20).mean()`
- [ ] Long-form 변환 및 v1 버전 기록
- [ ] Quality Gate: NaN row 제거 후 DuckDB 적재

### 2. Label Store 구현 (`src/quant/feature_store/labels.py`)
- [ ] v1 레이블 계산 로직 구현 (Look-ahead leakage 방지):
    - `fwd_ret_60d`: `(close.shift(-60) - close) / close`
    - `direction_60d`: `fwd_ret_60d > 0`
- [ ] Horizon 기반 유연한 계산 지원 (CLI 인자)
- [ ] Quality Gate: NaN row 제거 후 DuckDB 적재

### 3. CLI 및 Run Registry 연동 (`src/quant/cli.py`)
- [ ] `quant features` 커맨드 추가
    - `--feature-version` (default: v1) 인자 지원
    - `RunRegistry.run_start(kind="features")` 연동
- [ ] `quant labels` 커맨드 추가
    - `--label-version` (default: v1), `--horizon` (default: 60) 인자 지원
    - `RunRegistry.run_start(kind="labels")` 연동

## Verification Plan
### Automated Tests
- `uv run quant features --feature-version v1` 실행 후 `features_daily` 레코드 확인
- `uv run quant labels --label-version v1 --horizon 60` 실행 후 `labels` 레코드 확인

### Manual Verification
- DuckDB CLI를 이용한 데이터 정합성 확인
    - `SELECT * FROM features_daily WHERE symbol='AAPL' LIMIT 10;`
    - `SELECT * FROM labels WHERE symbol='AAPL' LIMIT 10;`
- SQLite `runs` 테이블 기록 확인

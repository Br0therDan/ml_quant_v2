# Artifact SUMMARY: Phase P3 - Feature Store (Features/Labels)

- **Date:** 2026-01-15
- **Phase:** Phase P3 (Feature Store)
- **Status:** PASS

## What Changed
- **Feature Store (`feature_store/features.py`)**: v1 피처 세트(`ret_1d~60d`, `vol_20d`, `gap_open`, `hl_range`, `volume_ratio_20d`) 계산 및 DuckDB `features_daily`(long-form) 적재 로직 구현.
- **Label Store (`feature_store/labels.py`)**: v1 레이블 세트(`fwd_ret_60d`, `direction_60d`) 계산 및 DuckDB `labels`(long-form) 적재 로직 구현. Look-ahead leakage 방지를 위한 shift 적용.
- **CLI (`cli.py`)**: `quant features`, `quant labels` 커맨드를 V2 모듈로 리팩토링하고 Run Registry 연동 완료.
- **Quality Gate**: 계산 불가능 구간(NaN)을 자동 제외(drop)하고 유효한 데이터만 저장하도록 구현.

## Artifacts Produced
- `src/quant/feature_store/features.py`
- `src/quant/feature_store/labels.py`
- [MODIFY] `src/quant/cli.py`

## Verification
- **실행 커맨드**:
    - `uv run quant features --feature-version v1`
    - `uv run quant labels --label-version v1 --horizon 60`
- **DuckDB 결과 (AAPL/MSFT)**:
    - `features_daily`: 8종 피처, 각 심볼당 약 6531 rows (13062 rows total for all features) - *참고: OHLCV 6591행 중 60일 윈도우 제외 시 약 6531행.*
    - `labels`: 2종 레이블, 각 심볼당 약 6531 rows (13062 rows total).
- **SQLite runs 기록**: `kind='features'`, `kind='labels'` 모두 `status='success'` 확인.

## Notes / Risks
- **Window Size**: 60일 윈도우 피처/레이블 계산으로 인해 데이터 초기 60일과 마지막 60일(레이블) 구간은 저장에서 제외됨.
- **Concurrency**: DuckDB 쓰기 작업 시 Streamlit 등 다른 프로세스가 DB를 점유하고 있으면 `IO Error(lock)`가 발생할 수 있으므로 실행 전 확인 필요.

## Next (P4)
- Phase P4: Model Training & Experiment Tracking
- SQLModel 기반 Experiment/Model 관리 모듈 구현
- Baseline 모델 학습 및 가중치 저장 연동

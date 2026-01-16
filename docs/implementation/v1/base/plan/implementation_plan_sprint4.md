# [Sprint 4] 레이블 및 데이터 분할 (Labels & Split) 구현 계획

본 계획서는 ML 모델 학습의 정답지가 될 레이블(Labels)을 생성하고, 학습/검증 데이터를 시계열적으로 분리(Split)하는 파이프라인 구축을 목표로 합니다.

## 1. 개요
Sprint 4에서는 미래 60거래일 수익률을 계산하여 레이블링하고, 데이터 누수(Leakage)가 없는 Walk-forward 분할 로직을 구현합니다.

## 2. 주요 변경 사항

### 2.1 DuckDB 스키마 확장
- [NEW] [labels](file:///Users/donghakim/ml_quant/src/quant/cli.py#149-153) 테이블 생성 (Long-form 구조)
  - [symbol](file:///Users/donghakim/ml_quant/src/quant/repos/symbol.py#43-45), [ts](file:///Users/donghakim/ml_quant/src/quant/db/timeseries.py#194-215), `label_name`, `label_value`, `label_version`, `computed_at`

### 2.2 레이블 생성 엔진
- [NEW] `src/quant/labels/make_labels.py`: 미래 N일 수익률 및 방향성 계산 로직
  - 지표: `fwd_ret_60d` (연속형), `direction_60d` (범주형: >0 일 때 1)

### 2.3 데이터 분할 (ML Split)
- [NEW] `src/quant/ml/splits.py`: 시계열 교차 검증(Time-series CV) 및 Walk-forward 분할기
  - 누수 방지를 위한 Purge(Embarrassingly Parallel) 기간 설정 지원

### 2.4 서비스 및 CLI 연동
- [NEW] `src/quant/services/label.py`: `LabelService`
- [MODIFY] [src/quant/cli.py](file:///Users/donghakim/ml_quant/src/quant/cli.py): `quant labels` 명령어 구현

## 3. 구현 단계 (Progress Dashboard)

| 단계 | 작업 내용 | 상태 |
| :--- | :--- | :--- |
| Phase 1 | DuckDB 스키마(labels) 정의 및 적용 | [ ] |
| Phase 2 | 레이블 생성 로직 구현 (fwd_ret_60d 등) | [ ] |
| Phase 3 | 시계열 데이터 분할 로직 (Walk-forward) 구현 | [ ] |
| Phase 4 | CLI 명령어 연동 및 Leakage 검증 | [ ] |

## 4. 세부 구현 계획

### Phase 1: Storage (DuckDB)
- [ ] [SeriesStore](file:///Users/donghakim/ml_quant/src/quant/db/timeseries.py#13-349)에 [labels](file:///Users/donghakim/ml_quant/src/quant/cli.py#149-153) 테이블 생성 SQL 및 `save_labels` 메서드 추가

### Phase 2: Labeling Logic
- [ ] 미래 시점의 Close 가격을 활용한 수익률 계산 (Look-ahead bias 방지 주의)
- [ ] `label_version="v1"` 관리

### Phase 3: ML Splitting
- [ ] 학습 기간(Window), 검증 기간(Horizon), 퍼지(Purge) 기간 설정 로직 구현
- [ ] 학습용 메타 정보(Index) 생성 기능

### Phase 4: CLI & Dashboard
- [ ] `quant labels --horizon 60` 명령어 활성화
- [ ] Streamlit 'Data Monitor'에 레이블 현황 추가

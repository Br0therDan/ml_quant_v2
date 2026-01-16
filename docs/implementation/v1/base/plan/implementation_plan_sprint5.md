# [Sprint 5] 베이스라인 학습 및 모델 레지스트리 (Baseline Train/Score) 구현 계획

본 계획서는 피처와 레이블을 이용하여 ML 모델을 학습(Train)하고, 학습된 모델을 관리하며, 이를 기반으로 예측(Score) 결과를 생성하는 파이프라인 구축을 목표로 합니다.

## 1. 개요
Sprint 5에서는 LightGBM을 주력 모델로 채택하여 베이스라인 모델을 학습합니다. 학습된 모델 파일은 로컬에 저장하고, 모델의 메타 정보와 성과 지표는 SQLite `models` 테이블에 기록합니다. 생성된 예측 결과는 DuckDB `predictions` 테이블에 영속화합니다.

## 2. 주요 변경 사항

### 2.1 의존성 추가
- `lightgbm`: 주력 ML 모델
- `scikit-learn`: 평가 지표 및 전처리 유틸리티
- `joblib`: 모델 파일 저장 및 로드

### 2.2 DuckDB 스키마 확장
- [NEW] `predictions` 테이블 생성
  - [symbol](file:///Users/donghakim/ml_quant/src/quant/repos/symbol.py#43-45), [ts](file:///Users/donghakim/ml_quant/src/quant/db/timeseries.py#220-241), `model_id`, `task_id`, [score](file:///Users/donghakim/ml_quant/src/quant/cli.py#176-180), `generated_at`

### 2.3 ML 파이프라인 모듈
- [NEW] `src/quant/ml/train.py`: LightGBM 기반 학습 함수
- [NEW] `src/quant/ml/score.py`: 학습된 모델을 활용한 추론 엔진
- [NEW] `src/quant/services/ml.py`: `MLService`
  - 데이터 준비 (Features + Labels Join)
  - [splits.py](file:///Users/donghakim/ml_quant/test_splits.py)를 활용한 데이터 분할
  - 학습 실행 및 [MetaStore](file:///Users/donghakim/ml_quant/src/quant/db/metastore.py#13-206) 기록
  - 예측 실행 및 [SeriesStore](file:///Users/donghakim/ml_quant/src/quant/db/timeseries.py#13-446) 기록

### 2.4 CLI 연동
- [MODIFY] [src/quant/cli.py](file:///Users/donghakim/ml_quant/src/quant/cli.py): `quant train`, `quant score` 명령어 구현

## 3. 구현 단계 (Progress Dashboard)

| 단계 | 작업 내용 | 상태 |
| :--- | :--- | :--- |
| Phase 1 | ML 의존성 추가 및 DuckDB predictions 테이블 정의 | [ ] |
| Phase 2 | 특징량-레이블 통합 및 데이터 분할 서비스 구현 | [ ] |
| Phase 3 | LightGBM 학습 및 모델 레지스트리(SQLite) 연동 | [ ] |
| Phase 4 | 추론 엔진 구축 및 예측 결과 영속화 (DuckDB) | [ ] |
| Phase 5 | CLI 명령어 연동 및 E2E 학습/예측 검증 | [ ] |

## 4. 세부 구현 계획

### Phase 1: Environment & Storage
- [ ] [pyproject.toml](file:///Users/donghakim/ml_quant/pyproject.toml) 업데이트 및 `uv sync`
- [ ] [SeriesStore](file:///Users/donghakim/ml_quant/src/quant/db/timeseries.py#13-446)에 `predictions` 테이블 생성 로직 추가

### Phase 2: Data Orchestration
- [ ] DuckDB에서 `features_daily`와 [labels](file:///Users/donghakim/ml_quant/src/quant/cli.py#150-168)를 Join 하여 학습용 `X`, `y` 생성
- [ ] [splits.py](file:///Users/donghakim/ml_quant/test_splits.py)의 Walk-forward 로직을 활용한 학습/검증 데이터셋 구성

### Phase 3: Model Logging
- [ ] 모델 파일을 `models/{model_id}.joblib` 형태로 저장
- [ ] `SQLModel`을 통해 `models` 테이블에 파라미터와 메트릭(Accuracy, Precision 등) 기록

### Phase 4: Scoring
- [ ] 특정 시점(`asof`) 이후의 데이터를 대상으로 예측 점수 생성
- [ ] `generated_at` 타임스탬프와 함께 DuckDB 저장

## 5. 예상 산출물 (Artifacts)
- 학습된 `.joblib` 모델 파일
- 모델 성능 지표가 포함된 SQLite DB
- 개별 심볼 및 시점별 예측 점수가 포함된 DuckDB
- Streamlit 'Predictions' 탭 활성화

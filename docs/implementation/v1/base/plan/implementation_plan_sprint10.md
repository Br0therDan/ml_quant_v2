# [Sprint 10] Denoise & Regularize (잡음 제거 및 일반화) 계획

본 계획서는 모델의 일반화 성능(Out-of-Sample Performance)을 높이기 위해 데이터 전처리 및 피처 선택 단계를 고도화하는 것을 목표로 합니다. 금융 데이터의 높은 노이즈(Noisy) 특성을 제어하기 위해 이상치 보정 및 안정적인 피처 선별 기법을 도입합니다.

## 1. 개요
금융 시계열 데이터는 극단값(Outlier)이 빈번하고, 피처의 설명력이 시간에 따라 변하는 특성이 있습니다. Sprint 10에서는 다음 두 가지 핵심 기법을 통해 모델의 강건성(Robustness)을 확보합니다.
1.  **Winsorization (Denoise)**: 극단적인 피처 값을 상/하한 임계값으로 클리핑하여 이상치의 영향을 줄입니다.
2.  **Stability Selection (Regularize)**: 데이터의 일부를 반복적으로 샘플링하여 피처 중요도를 평가함으로써, 우연에 의한 선택을 배제하고 일관되게 중요한 피처를 선별합니다.

## 2. 주요 변경 사항

### 2.1 Feature Engineering (Denoise)
- [MODIFY] [src/quant/services/feature.py](file:///Users/donghakim/ml_quant/src/quant/services/feature.py): [FeatureService](file:///Users/donghakim/ml_quant/src/quant/services/feature.py#13-64)
  - `winsorize` 옵션 추가: `quant features` 실행 시 Winsorization 적용 여부 및 임계값(예: 1% ~ 99%) 설정 기능 구현.
  - 전처리된 피처를 별도 버전(예: `v1_winsorized`)으로 저장하여 원본과 비교 가능하도록 지원.

### 2.2 Model Training (Regularize)
- [MODIFY] [src/quant/services/ml.py](file:///Users/donghakim/ml_quant/src/quant/services/ml.py): [MLService](file:///Users/donghakim/ml_quant/src/quant/services/ml.py#19-378)
  - `stability_selection` 메서드 구현: Randomized Lasso 또는 반복적인 Tree 기반 중요도 추출을 통해 피처 선택 수행.
  - 학습 파이프라인에 피처 선택 단계 통합: 선별된 Top-N 피처만 사용하여 최종 모델 학습.

### 2.3 CLI 연동
- [MODIFY] [src/quant/cli.py](file:///Users/donghakim/ml_quant/src/quant/cli.py)
  - `quant features`: `--winsorize-limits` 옵션 추가.
  - `quant train`: `--feature-selection` 및 `--stability-n-runs` 옵션 추가.

## 3. 구현 단계 (Progress Dashboard)

| 단계 | 작업 내용 | 상태 |
| :--- | :--- | :--- |
| Phase 1 | 피처 이상치 제어(Winsorization) 로직 구현 및 CLI 연동 | [ ] |
| Phase 2 | Stability Selection (피처 안정성 평가) 알고리즘 구현 | [ ] |
| Phase 3 | ML 파이프라인 통합 및 비교 실험 (OOS 성과 검증) | [ ] |

## 4. 세부 구현 계획

### Phase 1: Robust Preprocessing
- [ ] `scipy.stats.mstats.winsorize` 또는 `pandas.clip` 활용하여 전처리 로직 구현.
- [ ] DuckDB 저장 시 `feature_version`을 구분하여 원본 데이터 보존.

### Phase 2: Feature Selection
- [ ] 여러 번의 subsampling 후 모델을 학습시켜 피처 중요도(Feature Importance)의 평균/분산을 계산.
- [ ] 안정성 점수가 높은 상위 피처만 필터링하는 유틸리티 작성.

## 5. 예상 산출물 (Artifacts)
- 노이즈가 제거된 피처 데이터셋 (v2)
- 핵심 피처만 선별된 경량화 모델
- 개선된 OOS Sharpe Ratio 및 MDD 지표

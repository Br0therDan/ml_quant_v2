# [Sprint 6] Bull/Bear 전문가 앙상블 (Experts Ensemble) 구현 계획

본 계획서는 시장 상황(Bull/Bear)에 최적화된 개별 전문가 모델을 학습하고, 상황에 맞춰 적절한 모델을 선택(Gating)하여 예측 성능을 극대화하는 파이프라인 구축을 목표로 합니다.

## 1. 개요
단일 모델로 모든 시장 상황을 대응하기보다, 상승장(Bull)과 하락장(Bear)을 구분하여 각각의 전담 모델을 학습시킵니다. 추론 시점에는 현재 시장 상태를 진단하여 해당 전문가의 예측 점수를 우선적으로 활용합니다.

## 2. 주요 변경 사항

### 2.1 시장 진단 엔진
- [NEW] `src/quant/ml/experts.py`: 시장 국면 판단 로직
  - 기준: QQQ 등 벤치마크 지수의 이평선(SMA 20 vs 60) 또는 수익률 기반
  - 함수: `detect_market_regime(df_bench) -> "bull" | "bear"`

### 2.2 전문가 학습 (Task 분리)
- [MODIFY] `MLService.train_experts()`:
  - 시장 국면 데이터로 학습셋 필터링 (Bull 국면 데이터 -> Bull Expert 학습)
  - 모델 레지스트리에 `task_tag` (bull/bear) 기록

### 2.3 앙상블 추론 (Gating)
- [MODIFY] `MLService.score_ensemble()`:
  - 추론 시점의 시장 국면 판단
  - 해당 국면에 맞는 전문가 모델 로드 및 예측

### 2.4 CLI 연동
- [MODIFY] [src/quant/cli.py](file:///Users/donghakim/ml_quant/src/quant/cli.py): `quant train --task bull`, `quant score --ensemble` 등 옵션 강화

## 3. 구현 단계 (Progress Dashboard)

| 단계 | 작업 내용 | 상태 |
| :--- | :--- | :--- |
| Phase 1 | 시장 국면 진단 로직 (`experts.py`) 구현 | [ ] |
| Phase 2 | 국면별 데이터 분리 및 전문가 학습 로직 구현 | [ ] |
| Phase 3 | 게이팅 기반 앙상블 추론 서비스 고도화 | [ ] |
| Phase 4 | CLI 명령어 연동 및 Bull/Bear 성능 비교 검증 | [ ] |

## 4. 세부 구현 계획

### Phase 1: Regime Detection
- [ ] 벤치마크(QQQ) 데이터를 활용한 간단한 SMA 크로스오버 국면 판단기 작성
- [ ] 특징량/레이블 데이터에 국면 태그(Regime)를 조인하는 유틸리티 구현

### Phase 2: Expert Training
- [ ] [MLService](file:///Users/donghakim/ml_quant/src/quant/services/ml.py#17-189)에 `train_experts` 메서드 추가
- [ ] 학습 시 [Model](file:///Users/donghakim/ml_quant/src/quant/models/meta.py#32-47) 테이블의 `task_id` 또는 `experiment_id`를 활용하여 전문가 구분

### Phase 3: Ensemble Scoring
- [ ] 추론 시 현재 국면을 자동으로 판별하고 모델을 스위칭하는 로직
- [ ] 예측 결과([predictions](file:///Users/donghakim/ml_quant/src/quant/db/timeseries.py#514-524)) 테이블에 `task_id`를 "bull_expert", "bear_expert" 등으로 기록

## 5. 예상 산출물 (Artifacts)
- 국면별 전문가 모델 파일군
- 국면 진단 결과가 포함된 예측 데이터셋
- Bull/Bear 모델별 성능 비교 리포트

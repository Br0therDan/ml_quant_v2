# [Sprint 3] 특징량 파이프라인 (Feature Engineering) 구현 계획

본 계획서는 [ohlcv](file:///Users/donghakim/ml_quant/src/quant/db/timeseries.py#159-169) 데이터를 기반으로 다양한 ML 모델의 입력값이 될 특징량(Features)을 생성하고 관리하는 파이프라인 구축을 목표로 합니다.

## 1. 개요
Sprint 3에서는 기술적 분석 지표(Momentum, Volatility, Trend 등)를 계산하고, 이를 DuckDB의 `features_daily` 테이블에 영속화하는 시스템을 구축합니다. `feature_version` 개념을 도입하여 실험의 재현성을 보장합니다.

## 2. 주요 변경 사항

### 2.1 DuckDB 스키마 확장
- [NEW] `features_daily` 테이블 생성 (Long-form 구조)
  - [symbol](file:///Users/donghakim/ml_quant/src/quant/repos/symbol.py#43-45), [ts](file:///Users/donghakim/ml_quant/src/quant/db/timeseries.py#179-200), `feature_name`, `feature_value`, `feature_version`, `computed_at`

### 2.2 피처 계산 엔진 (Feature Engine)
- [NEW] `src/quant/features/definitions.py`: 순수 Pandas 기반의 기술적 지표 계산 로직 라이브러리
  - 지표 후보: Returns(1d, 5d, 20d, 60d), RSI, SMA, EMA, ATR, Bollinger Bands, Gap % 등

### 2.3 서비스 및 CLI 연동
- [NEW] `src/quant/services/feature.py`: `FeatureService`
  - 전체 심볼 순회 및 피처 계산/저장 오케스트레이션
- [MODIFY] [src/quant/cli.py](file:///Users/donghakim/ml_quant/src/quant/cli.py): `quant features` 명령어 구현
  - `--symbols`, `--force-refresh`, `--version` 등의 옵션 제공

## 3. 구현 단계 (Progress Dashboard)

| 단계 | 작업 내용 | 상태 |
| :--- | :--- | :--- |
| Phase 1 | DuckDB 스키마(features_daily) 정의 및 적용 | [ ] |
| Phase 2 | 기술적 지표 계산 로직 구현 (definitions.py) | [ ] |
| Phase 3 | 피처 계산 서비스(FeatureService) 구축 | [ ] |
| Phase 4 | CLI 명령어 연동 및 E2E 검증 | [ ] |

## 4. 세부 구현 계획

### Phase 1: Storage (DuckDB)
- [ ] [src/quant/db/timeseries.py](file:///Users/donghakim/ml_quant/src/quant/db/timeseries.py)에 `features_daily` 테이블 생성 SQL 추가
- [ ] 초기화 로직([_init_db](file:///Users/donghakim/ml_quant/src/quant/db/metastore.py#20-42)) 업데이트

### Phase 2: Feature Definitions
- [ ] 수익률 시리즈: `ret_1d`, `ret_5d`, `ret_20d`, `ret_60d`
- [ ] 추세/모멘텀: `SMA(20/60)`, `EMA(20)`, `RSI(14)`
- [ ] 변동성/기타: `ATR(14)`, `DayRange_pct`, `Gap_pct`

### Phase 3: Domain Service
- [ ] 저장소에서 OHLCV 로드 -> 피처 계산 -> `features_daily` Upsert 흐름 구현
- [ ] 스냅샷 관리를 위한 `feature_version="v1"` 기본값 설정

### Phase 4: CLI & Dashboard
- [ ] `quant features` 명령어 활성화
- [ ] Streamlit 'Data Monitor' 탭에서 피처 데이터 생성 여부 시각화 추가

## 5. 예상 산출물 (Artifacts)
- `features_daily` 테이블이 포함된 DuckDB
- 재사용 가능한 특징량 계산 라이브러리
- 피처 생성 로그 및 대시보드 업데이트

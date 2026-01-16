# [Sprint 7] 포트폴리오 결정 엔진 (Portfolio Decision Engine) 구현 계획

본 계획서는 분산된 종목별 예측 점수(ML Scores)를 통합하여, 실제 투자 가능한 종목 선정(Top-K) 및 비중 배분(Sizing) 지시서를 생성하는 엔진 구축을 목표로 합니다.

## 1. 개요
Sprint 6까지 완성된 예측 엔진은 "각 종목이 오를 확률"을 제공합니다. Sprint 7에서는 이 확률들을 비교하여 최적의 포트폴리오 구성을 결정합니다. 예를 들어, 예측 점수가 가장 높은 상위 3개 종목을 선정하고, 리스크를 고려하여 비중을 나누는 과정을 자동화합니다.

## 2. 주요 변경 사항

### 2.1 포트폴리오 서비스
- [NEW] `src/quant/services/portfolio.py`: `PortfolioService`
  - `select_top_k(scores, k=3)`: 점수 기반 상위 종목 필터링
  - `calculate_sizing(symbols, method="equal")`: 비중 산출 (Equal Weight 또는 Volatility Inverse 등)
  - `generate_recommendation(date)`: 특정 시점의 추천 포트폴리오 생성

### 2.2 DuckDB 스키마 확장
- [NEW] `portfolio_decisions` 테이블 생성
  - [date](file:///Users/donghakim/ml_quant/src/quant/db/timeseries.py#244-252), [symbol](file:///Users/donghakim/ml_quant/src/quant/repos/symbol.py#43-45), `weight`, [score](file:///Users/donghakim/ml_quant/src/quant/cli.py#212-245), `model_id`, `decision_at`
  - 특정 날짜에 어떤 근거로 어떤 비중이 결정되었는지 기록

### 2.3 CLI 연동
- [MODIFY] [src/quant/cli.py](file:///Users/donghakim/ml_quant/src/quant/cli.py): `quant recommend` 명령어 구현
  - 최신 데이터를 기준으로 내일의 투자 필수 리스트 출력 및 DB 저장

### 2.4 대시보드 강화
- [MODIFY] Streamlit에 'Portfolio' 탭 추가
  - 현재 추천 종목 및 비중 히스토리 시각화

## 3. 구현 단계 (Progress Dashboard)

| 단계 | 작업 내용 | 상태 |
| :--- | :--- | :--- |
| Phase 1 | DuckDB `portfolio_decisions` 테이블 정의 | [ ] |
| Phase 2 | 종목 선정(Top-K) 및 비중 배분(Sizing) 로직 구현 | [ ] |
| Phase 3 | `PortfolioService` 통합 및 추천 엔진 구축 | [ ] |
| Phase 4 | CLI 명령어 (`quant recommend`) 연동 및 검증 | [ ] |
| Phase 5 | Streamlit 포트폴리오 시각화 탭 구현 | [ ] |

## 4. 세부 구현 계획

### Phase 1: Storage Layer
- [ ] [SeriesStore](file:///Users/donghakim/ml_quant/src/quant/db/timeseries.py#14-524)에 `portfolio_decisions` 테이블 생성 및 저장/조회 메서드 추가

### Phase 2: Decision Logic
- [ ] 단순 동일 비중(Equal Weight) 및 리스크 기반(Volatility 기반) 사이징 엔진 작성
- [ ] 시뮬레이션 시 발생할 수 있는 거래 비용 등을 고려한 최소 비중 컷오프(Cut-off) 도입

### Phase 3: Recommendation Engine
- [ ] 가장 최신의 예측 점수(Ensemble score)를 취합하여 오늘의 TOP 추천 리스트 생성 로직 완성

## 5. 예상 산출물 (Artifacts)
- 날짜별 포트폴리오 구성 비중 데이터 (DuckDB)
- CLI 추천 리스트 콘솔 출력 레이아웃
- Streamlit 포트폴리오 비중 추이 차트

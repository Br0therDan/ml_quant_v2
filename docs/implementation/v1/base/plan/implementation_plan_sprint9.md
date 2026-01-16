# [Sprint 9] Streamlit Read-Only Dashboard 고도화 계획

본 계획서는 기존 단일 파일 형태의 Streamlit 대시보드를 멀티 페이지로 전환하고, 수집된 데이터와 성능 분석 결과를 사용자 친화적으로 시각화하는 것을 목표로 합니다.

## 1. 개요
전략 실행의 전 과정(수집-피처-라벨-예측-포트폴리오-백테스트)이 데이터베이스에 영속화되어 있습니다. Sprint 9에서는 이를 "읽기 전용"으로 시각화하여, 파이프라인의 건강 상태와 전략 성능을 입체적으로 모니터링할 수 있는 완성도 높은 UI를 구축합니다.

## 2. 주요 변경 사항

### 2.1 대시보드 구조화 (Multi-page)
- [app/streamlit_app.py](file:///Users/donghakim/ml_quant/app/streamlit_app.py): 메인 대시보드 (Overview)
- `app/pages/1_Data_Monitor.py`: OHLCV, Features, Labels 데이터 현황 상세
- [app/pages/2_Predictions.py](file:///Users/donghakim/ml_quant/app/pages/2_Predictions.py): 상위 예측 점수 및 전문가 모델 분석
- `app/pages/3_Backtest_Summary.py`: 에쿼티 커브, 수익 성과 지표 상세 분석

### 2.2 기능 고도화
- [NEW] **Overview (Home)**: 전체 시스템 상태 요약 및 최근 백테스트 성과 카드 표시
- [NEW] **Interactive Equity Curve**: 특정 백테스트 런(run_id) 선택 시 차트 업데이트 및 벤치마크 비교
- [NEW] **Risk Analysis**: MDD 히트맵 또는 변동성 추이 시각화 보완
- [NEW] **Data Quality Flag**: 데이터 누락 또는 이상치 발생 시 경고 표시 연동

## 3. 구현 단계 (Progress Dashboard)

| 단계 | 작업 내용 | 상태 |
| :--- | :--- | :--- |
| Phase 1 | Streamlit 멀티 페이지 폴더 구조 생성 및 파일 분리 | [ ] |
| Phase 2 | Overview 페이지 (시스템 상태 요약) 구현 | [ ] |
| Phase 3 | 데이터 모니터링 (OHLCV/F/L) 상세 분석 페이지 고도화 | [ ] |
| Phase 4 | 예측 점수 및 전문가 앙상블 분석 페이지 구현 | [ ] |
| Phase 5 | 백테스트 상세 리포트 및 에쿼티 커브 심화 시각화 | [ ] |

## 4. 세부 구현 계획

### Phase 1: Structure Reorg
- [ ] `app/pages/` 디렉토리 생성 및 기존 탭 로직을 독립 파일로 이관
- [ ] 공통 데이터 로드 로직 (`safe_duck_query` 등) 유틸리티화

### Phase 2: Professional UI/UX
- [ ] `st.metric` 및 카드 디자인을 활용하여 CAGR, Sharpe 등을 시각적으로 강조
- [ ] 파이썬 시각화 라이브러리(Plotly 또는 Altair)를 활용한 인터랙티브 차트 도입

## 5. 예상 산출물 (Artifacts)
- 구조화된 멀티 페이지 Streamlit 애플리케이션
- 시스템 통합 대시보드 결과물

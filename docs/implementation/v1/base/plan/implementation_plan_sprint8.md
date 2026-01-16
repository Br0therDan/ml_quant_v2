# [Sprint 8] 백테스트 엔진 (Backtest Engine) v1 구현 계획

본 계획서는 포트폴리오 결정 엔진(Sprint 7)의 결과를 바탕으로 과거 데이터를 시뮬레이션하여 전략의 실효성을 검증하고, 성과 지표(CAGR, Sharpe, MDD 등)를 산출하는 백테스트 엔진 구축을 목표로 합니다.

## 1. 개요
백테스트 엔진은 과거 특정 기간 동안 [portfolio_decisions](file:///Users/donghakim/ml_quant/src/quant/db/timeseries.py#572-580)에 기록된 비중대로 매매를 수행했을 때의 가상 수익률을 계산합니다. 종가 기준 매매를 가정하며, 슬리피지(Slippage) 및 수수료 요소를 고려할 수 있는 구조로 설계합니다.

## 2. 주요 변경 사항

### 2.1 백테스트 서비스
- [NEW] `src/quant/services/backtest.py`: `BacktestService`
  - `run_backtest(start_date, end_date)`: 기간별 시뮬레이션 실행
  - `calculate_metrics(returns_series)`: CAGR, Sharpe Ratio, MDD, Win Rate 등 산출
  - `generate_equity_curve()`: 일별 자산 가치 변화 트래킹

### 2.2 DuckDB 스키마 확정
- [NEW] `backtest_summary` 테이블 생성 (일부 기구현 확인)
  - `run_id`, `from_ts`, `to_ts`, `cagr`, `sharpe`, `max_dd`, `num_trades`, `created_at`
- [NEW] `backtest_trades` 테이블 생성
  - `run_id`, [date](file:///Users/donghakim/ml_quant/src/quant/db/timeseries.py#259-267), [symbol](file:///Users/donghakim/ml_quant/src/quant/repos/symbol.py#43-45), `action` (buy/sell), [price](file:///Users/donghakim/ml_quant/src/quant/services/market_data.py#20-72), `weight`

### 2.3 CLI 연동
- [MODIFY] [src/quant/cli.py](file:///Users/donghakim/ml_quant/src/quant/cli.py): `quant backtest` 명령어 구현
  - 기간 설정을 통해 백테스트 수행 및 성과 요약 출력

### 2.4 대시보드 시각화
- [MODIFY] Streamlit 'Backtest Summary' 탭 활성화
  - 누적 수익률 차트(Equity Curve) 및 주요 지표 테이블 표시

## 3. 구현 단계 (Progress Dashboard)

| 단계 | 작업 내용 | 상태 |
| :--- | :--- | :--- |
| Phase 1 | DuckDB 성과 및 매매 이력 테이블 정의 | [ ] |
| Phase 2 | 시뮬레이션 엔진 및 수익률 계산 로직 구현 | [ ] |
| Phase 3 | `BacktestService` 및 지표 산출 로직 구축 | [ ] |
| Phase 4 | CLI 명령어 (`quant backtest`) 연동 및 검증 | [ ] |
| Phase 5 | Streamlit 성과 차트 및 리포트 시각화 구현 | [ ] |

## 4. 세부 구현 계획

### Phase 1: Storage Layer
- [ ] [SeriesStore](file:///Users/donghakim/ml_quant/src/quant/db/timeseries.py#14-580)에 `backtest_summary`, `backtest_trades` 테이블 생성 및 관리 메서드 추가

### Phase 2: Core Simulation
- [ ] 일별 리밸런싱 및 수익률 복리 계산 로직 작성
- [ ] 벤치마크(QQQ) 대비 초과 수익률(Alpha) 계산 포함

### Phase 3: Metrics Engine
- [ ] `scipy` 등을 활용하여 리스크 지표(Sharpe, Tail Risk) 산출 유틸리티 구축

## 5. 예상 산출물 (Artifacts)
- 백테스트 성과 요약 정보 (DuckDB)
- 누적 수익률 시각화 결과물
- 전략 성과 상세 리포트

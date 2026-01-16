# Artifact SUMMARY: Phase P5 - Backtest Engine v1

- **Date:** 2026-01-15
- **Phase:** Phase P5 (Backtest Engine)
- **Status:** PASS

## What Changed
- **Backtest Engine (`backtest_engine/engine.py`)**: 
    - DuckDB `targets`의 `approved=true` 데이터를 기반으로 한 리밸런싱 시뮬레이터 구현.
    - **T close 리밸런싱 / T+1 PnL 반영** 로직 적용.
    - **Daily Ledger 방식**으로 `backtest_trades` 적재 (일별 비중, 기여도, 비용).
    - DuckDB Python API 및 **Raw SQL**을 사용한 결과 적재 (SQLAlchemy 의존성 제거).
- **Strategy Loader (`strategy_lab/loader.py`)**: 미래 확장을 위한 `model_score` 신호 타입 Hook 추가.
- **CLI (`cli.py`)**: `quant backtest` 커맨드 구현 및 Run Registry 연동.
- **의존성**: DuckDB 엔진 연결 호환성을 위해 `duckdb-engine` 패키지가 환경에 추가됨.

## Artifacts Produced
- `src/quant/backtest_engine/engine.py`
- [MODIFY] `src/quant/strategy_lab/loader.py`
- [MODIFY] `src/quant/cli.py`

## Verification
- **실행 커맨드**:
    - [성공] `uv run quant backtest --strategy strategies/example.yaml --from 2026-01-14 --to 2026-01-14`
    - [성공(No Results)] `uv run quant backtest --strategy strategies/example.yaml --from 2024-01-01 --to 2025-12-31`
- **DuckDB 결과 검증**:
    - `backtest_summary`: CAGR, Sharpe, MDD 등 지표가 정상 적재됨.
    - `backtest_trades`: AAPL, MSFT에 대한 일별 비중(qty) 및 기여도(pnl_pct) 확인됨.
- **SQLite runs 기록**: `kind='backtest'`, `status='success'` 확인.

## Notes / Risks
- **SQL NaN 대응**: 파이썬 `NaN` 값이 SQL 구문 오류를 일으키지 않도록 `NULL`/0 변환 로직 적용.
- **Ledger 포맷**: `backtest_trades`의 `qty` 필드에 비중을, `pnl_pct` 필드에 일별 수익 기여도를 기록함.

## Next (P6)
- Phase P6: Portfolio Analyzer (Visualizer)
- 백테스트 결과(Equity Curve, DD) 시각화
- 전략별 성과 비교 기능

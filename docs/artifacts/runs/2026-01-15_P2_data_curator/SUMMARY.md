# Artifact SUMMARY: Phase P2 - Data Curator (Ingest)

- **Date:** 2026-01-15
- **Phase:** Phase P2 (Data Curator)
- **Status:** PASS

## What Changed
- **Alpha Vantage Provider (`provider.py`)**: `tenacity`를 활용한 Retry 및 Exponential Backoff 로직 구현. 응답 유효성 검사 강화.
- **Quality Gate (`quality_gate.py`)**: OHLCV 필드 존재 여부, NaN 비율, 중복 타임스탬프 등을 검사하는 게이트웨이 추가.
- **DuckDB Ingester (`ingest.py`)**: `symbol, ts` PK 기반의 증분 적재(Incremental Load) 및 Upsert(Delete & Insert) 로직 구현. DuckDB와 Pandas의 안정적인 연동을 위해 임시 테이블 및 명시적 타입 캐스팅 적용.
- **CLI (`cli.py`)**: `quant ingest` 커맨드를 V2 모듈로 교체하고, 모든 실행을 Run Registry(SQLite)에 기록하도록 연동.
- **Compatibility**: V1 `SeriesStore`가 V2 DuckDB 테이블 스키마를 파괴하지 않도록 초기화 로직 비활성화.

## Artifacts Produced
- `src/quant/data_curator/provider.py`
- `src/quant/data_curator/quality_gate.py`
- `src/quant/data_curator/ingest.py`
- [MODIFY] `src/quant/cli.py`
- [MODIFY] `src/quant/db/timeseries.py`

## Verification (Done Criteria)
- **실행 커맨드**: `uv run quant ingest --symbols AAPL --symbols MSFT`
- **DB 검증 쿼리 결과**:
  - `ohlcv` row 증가: AAPL (6591 rows), MSFT (6591 rows) 적재 완료.
  - SQLite `runs` 기록: `kind='ingest', status='success'` 확인.

## Notes / Risks
- **Risk**: Alpha Vantage의 API 일일 호출 한도(Rate Limit)에 도달할 경우 `tenacity` 리트라이가 발생하며 대기 시간이 길어질 수 있음.
- **Note**: DuckDB의 `INSERT OR REPLACE`가 특정 환경에서 불안정한 이슈가 있어 `DELETE & INSERT` 트랜잭션 방식으로 구현하여 안정성을 확보함.

## Next (P3)
- Phase P3: Feature Engineering (Daily Features) 구현
- Technical Indicators (MA, RSI, etc.) 추가
- DuckDB `features_daily` 테이블 적재 연동

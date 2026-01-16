# Walkthrough: V2 Phase P2 - Data Curator (Ingest)

## 1. 개요
데이터 수집 및 적재 계층인 Phase P2를 완료하였습니다. 안정적인 API 호출과 DuckDB로의 데이터 정합성 보장 적재가 핵심입니다.

## 2. 주요 구현 내용

### 2.1 Alpha Vantage Provider
- `tenacity` 기반의 리트라이 로직을 통해 Rate limit 및 네트워크 오류에 대응합니다.
- 데이터 유효성 검사를 통해 비정상적인 응답(Error Message 등)을 사전에 차단합니다.

### 2.2 DuckDB Ingest (Upsert)
- `symbol, ts` 복합 PK를 기준으로 기존 데이터를 삭제 후 삽입하는 트랜잭션 방식을 사용합니다.
- [latest_ts](file:///Users/donghakim/ml_quant/src/quant/data_curator/ingest.py#19-32)를 조회하여 필요한 범위만 수집하는 증분 적재 모드를 기본으로 합니다.

### 2.3 Quality Gate
- 수집된 데이터의 NaN 비율, 가격의 양수 여부, 중복 타임스탬프 등을 검증하여 저품질 데이터의 유입을 막습니다.

## 3. 검증 증거

### 3.1 CLI 실행 결과
```bash
$ uv run quant ingest --symbols AAPL --symbols MSFT
# ...
# ⠹ Ingesting AAPL (1/2)... INFO Successfully ingested 6591 rows for AAPL
# ⠹ Ingesting MSFT (2/2)... INFO Successfully ingested 6591 rows for MSFT
# Ingestion Complete for 2 symbols
```

### 3.2 DB 적재 상태 확인
DuckDB 쿼리 결과:
| symbol | count(*) |
|---|---|
| AAPL | 6591 |
| MSFT | 6591 |

SQLite `runs` 로그:
- `3fbd13ac-a51e-45b7-9f76-242d6f42955d | ingest | success | 2026-01-15 11:00:17`

## 4. 관련 파일
- [ingest.py](file:///Users/donghakim/ml_quant/src/quant/data_curator/ingest.py)
- [provider.py](file:///Users/donghakim/ml_quant/src/quant/data_curator/provider.py)
- [quality_gate.py](file:///Users/donghakim/ml_quant/src/quant/data_curator/quality_gate.py)
- [SUMMARY.md](file:///Users/donghakim/ml_quant/artifacts/runs/2026-01-15_P2_data_curator/SUMMARY.md)

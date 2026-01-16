# Sprint Implementation Plan: V2 Phase P2 - Data Curator (Ingest)

**Version:** v1.0.0  
**Date:** 2026-01-15  
**Last Updated:** 2026-01-15

---

## 1. Executive Summary
V2 시스템의 데이터 수집 계층인 `data_curator`를 구축한다. Alpha Vantage API를 안정적으로 호출(Retry/Backoff)하고, 수집된 OHLCV 데이터를 DuckDB에 계약된 스키마에 맞춰 증분 적재(Incremental Load)한다. 모든 과정은 Quality Gate를 거쳐 정합성을 보장하며, Run Registry에 기록된다.

---

## 2. Objective
- 안정적인 데이터 수집 레이어 제공 (Retry, Backoff, Validation)
- DuckDB `ohlcv` 테이블에 대한 Upsert 및 증분 적재 로직 구현
- 데이터 품질 검증(Quality Gate) 자동화
- `quant ingest` CLI를 통한 워크플로우 통합

---

## 3. Progress Dashboard

| Phase | Scope | Status |
|---|---|---|
| P2-1 | Alpha Vantage Provider (Retry/Validation) | [ ] |
| P2-2 | Quality Gate Logic | [ ] |
| P2-3 | DuckDB Ingest (Upsert/Incremental) | [ ] |
| P2-4 | CLI Integration & Run Tracking | [ ] |
| P2-5 | Artifact Snapshot (SUMMARY.md) | [ ] |

---

## 4. Implementation Plan

### 4.1 Alpha Vantage Provider
- [ ] `src/quant/data_curator/provider.py` 생성
- [ ] `requests` + `tenacity`를 활용한 Retry(Rate limit 대응) 및 Exponential Backoff 구현
- [ ] 응답 JSON의 필수 키(Meta Data, Time Series) 존재 여부 검사 로직 추가

### 4.2 Quality Gate Logic
- [ ] `src/quant/data_curator/quality_gate.py` 생성
- [ ] `check_ohlcv(df)`: 
    - Essential columns 존재 여부
    - OHLCV 값이 0 이하인지 검사
    - 중복된 Timestamp 존재 여부
- [ ] 검증 실패 시 `DataQualityError` 발생

### 4.3 DuckDB Ingest Logic
- [ ] `src/quant/data_curator/ingest.py` 생성
- [ ] `get_latest_ts(symbol)`: DuckDB에서 해당 심볼의 마지막 날짜 조회
- [ ] `ingest_symbol(symbol)`:
    - 마지막 날짜 이후의 데이터만 요청 (outputsize=compact/full 판단)
    - Quality Gate 통과 후 DuckDB `INSERT OR REPLACE` (또는 DELETE then INSERT) 수행

### 4.4 CLI Integration
- [ ] `src/quant/cli.py` 수정
- [ ] `ingest` 커맨드 고도화:
    - Run Registry 시작 (`run_start`)
    - 루프 내에서 각 심볼 처리
    - 예외 발생 시 `run_fail` 및 `error_text` 기록
    - 성공 시 `run_success` 

### 4.5 Artifact Snapshot
- [ ] `artifacts/runs/<YYYY-MM-DD>_P2_data_curator/SUMMARY.md` 생성
- [ ] DB 검증 쿼리 결과 및 실행 로그 포함

---

## 5. Expected Artifacts
- `src/quant/data_curator/provider.py` [NEW]
- `src/quant/data_curator/ingest.py` [NEW]
- `src/quant/data_curator/quality_gate.py` [NEW]
- `src/quant/cli.py` [MODIFY]
- `artifacts/runs/*/SUMMARY.md` [NEW]

---

## 6. Done Criteria
- `quant ingest --symbols AAPL MSFT` 실행 성공
- DuckDB `ohlcv` 테이블에 최신 데이터가 누적됨
- SQLite `runs` 테이블에 `ingest` 타입의 성공/실패 기록이 실시간으로 남음

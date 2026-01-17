# [PLAN] 레거시 제거 및 Data Curator 안정화 (V1 -> V2 전환 완료)

- **Version**: 1.0.0
- **Date**: 2026-01-17
- **Status**: DRAFT (Review Required)

## 1. Executive Summary
현재 ML Quant V2는 핵심 기능 구현이 완료되었으나, 데이터 수집 및 관리 계층에서 V1의 레거시 구조(`market_data/`, `quant.services.market_data`)가 병행 사용되고 있어 아키텍처 혼선과 기능적 결함(Adjusted OHLC 미흡)이 존재합니다. 본 계획은 V1의 정교한 데이터 설계 요소를 V2 `data_curator`로 완전히 흡수하고 레거시를 제거하여 시스템 안정성과 재현성을 확보하는 것을 목표로 합니다.

## 2. Objective
1. **레거시 제거**: `./market_data/` 및 `src/quant/services/` 의 잔재를 100% 제거.
2. **Data Curator 고도화**: V1의 AV API 응답 매핑 로직(`_map_av_overview`) 및 검색 기능을 `data_curator` 모듈로 이관.
3. **OHLCV 데이터 무결성 확보**: 주식 액면분할 및 배당을 반영한 Adjusted OHLC(Open, High, Low, Close) 저장 로직 구현.
4. **정적 데이터 관리**: `market_data/static`에 의존하는 심볼 데이터를 V2 내부 경로로 이관.

## 3. Progress Dashboard

| Category     | Task                          | Status      | Note                                |
| ------------ | ----------------------------- | ----------- | ----------------------------------- |
| **Analysis** | Legacy Usage Scan             | DONE        | CLI/Metastore 등에서 혼용 확인      |
| **Analysis** | Adjustment Logic Comparison   | DONE        | V2의 Raw OHLC 저장 문제 확인        |
| **Logic**    | AV Overview Mapping Migration | NOT STARTED | V1 `client.py` 로직 참조 예정       |
| **Logic**    | Adjusted OHLC Implementation  | NOT STARTED | `adj_factor` 계산 로직 도입         |
| **Cleanup**  | Legacy Code Removal           | NOT STARTED | ./market_data, ./src/quant/services |

## 4. Implementation Plan

### Step 1: Data Curator Logic Migration
- [ ] **`AlphaVantageProvider` 확장**:
  - `_map_av_overview` 메서드 추가 (V1 `LocalMarketDataClient` 로직 이관).
  - `symbol_search` API 호출 메서드 추가.
  - `get_daily_ohlcv` 수정: `7. dividend amount`, `8. split coefficient` 포함 및 필드 추출.
- [ ] **Adjusted Price 계산 구현**:
  - `DataIngester` 또는 `Provider` 내부에 `adj_factor = (adjusted_close / close)` 기반의 OHLC 조정 로직 추가.
  - 최종 DuckDB `ohlcv` 테이블에 `open`, `high`, `low`, `close`가 모두 조정된 값으로 저장되도록 보장.
- [ ] **Symbol Search Service 구현**:
  - `data_curator` 내부에 로컬 DB와 API 검색을 병합하는 로직 구현.

### Step 2: Static Data & Metastore Refactoring
- [ ] **Static Assets 이동**:
  - `market_data/static/*.csv` -> `src/quant/data_curator/static/`으로 이동.
- [ ] **`metastore.py` 업데이트**:
  - `seed_from_csv` 경로 수정 및 레거시 `market_data` 의존성 제거.

### Step 3: API & CLI Integration
- [ ] **`src/quant/cli.py` 수정**:
  - `MarketDataService` 의존성을 `DataIngester` 및 `MetaStore`로 교체.
- [ ] **`src/quant/interactive.py` & `repos/symbol.py` 수정**:
  - 레거시 서비스/클라이언트 임포트 제거 및 V2 모듈로 교체.

### Step 4: Final Cleanup & Validation
- [ ] **삭제**: `./market_data/` 폴더 전체 삭제.
- [ ] **삭제**: `src/quant/services/market_data.py` 파일 및 관련 서비스 모듈 삭제 (V2 SSOT에 따라 팀별 모듈 구조로 유지).
- [ ] **검증**: `AAPL` 등 액면분할 이력이 있는 유니버스 풀 인제스팅 후 차트 이상 여부 확인.
- [ ] **검증**: `pytest`를 통한 Data Ingestion 및 Quality Gate 통과 여부 확인.

## 5. Risks & Notes
- **데이터 일관성**: 기존 `ohlcv` 테이블에 Raw 데이터가 섞여 있을 수 있으므로, 재구축 시 `DROP TABLE` 또는 `TRUNCATE` 후 신규 로직으로 full-ingest 권장.
- **API 레이트 리밋**: Adjusted OHLC 계산을 위해 'full' 데이터를 재수집할 경우 Alpha Vantage API 호출량 급증 주의.
- **SSOT 준수**: 모든 변경 사항은 `V2_SYSTEM_SPEC.md`에 정의된 DuckDB/SQLite 스키마를 준수함.

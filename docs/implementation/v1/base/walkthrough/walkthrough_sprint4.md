# Walkthrough: 마켓 데이터 수집 및 저장 계층 분리 완료

본 레포트는 `market_data` 라이브러리의 역할을 단순화하고, 데이터베이스 관리 및 비즈니스 로직을 `src/quant`로 이관하여 시스템 아키텍처를 고도화한 결과를 요약합니다.

## 1. 주요 개선 사항

### 아키텍처 계층화 (Layered Architecture)
- **market_data (Provider)**: 외부 API(Alpha Vantage) 호출 기능만 남기고 경량화했습니다. 이제 DB 저장소 의존성이 전혀 없습니다.
- **src/quant/db (Persistence)**: `MetaStore`와 `SeriesStore`를 이관하여 데이터 영속성 관리를 일원화했습니다.
- **src/quant/services/market_data.py**: [MarketDataService](file:///Users/donghakim/ml_quant/src/quant/services/market_data.py)를 신설하여 수집, 저장, 데이터 보강(Join) 로직을 통합 관리합니다.
- **src/quant/features/definitions.py**: [definitions.py](file:///Users/donghakim/ml_quant/src/quant/features/definitions.py)에 기술적 분석 지표 12종을 구현했습니다.
- **src/quant/labels/make_labels.py**: [make_labels.py](file:///Users/donghakim/ml_quant/src/quant/labels/make_labels.py)에서 미래 60일 수익률(`fwd_ret_60d`)과 방향성(`direction_60d`) 레이블을 생성합니다.
- **src/quant/ml/splits.py**: [splits.py](file:///Users/donghakim/ml_quant/src/quant/ml/splits.py)에서 데이터 누수 방지를 위한 **Walk-forward** 및 **Purge Gap** 시계열 분할 로직을 구현했습니다.
- **src/quant/services/label.py**: [LabelService](file:///Users/donghakim/ml_quant/src/quant/services/label.py)를 통해 레이블링 자동화 및 DuckDB 저장을 관리합니다.

### 데이터 모델 및 인프라 고도화
- **DuckDB features_daily**: Long-form 데이터 구조를 도입하여 다양한 버전의 특징량을 유연하게 관리합니다.
- **SQLModel SSOT**: `market_data/models` 폴더를 삭제하고 [src/quant/models](file:///Users/donghakim/ml_quant/src/quant/models/)를 직접 참조하도록 정리했습니다.
- **TypeError & Assertion Failure 해결**: 복잡한 Upsert 로직을 `ON CONFLICT` 기반으로 개선하여 DuckDB 내부 오류를 원천 차단했습니다.

### 이슈 해결
- **0 row 수집 문제**: DB 파일 경로 설정(`quant_duckdb_path`)이 라이브러리와 서비스 간에 불일치하던 문제를 `config.py` 중심으로 통합하여 해결했습니다.
- **TypeError (search_hybrid)**: 메서드 시그니처 불일치를 하이브리드 검색 로직의 서비스 계층 이관을 통해 해결했습니다.

---

## 2. 검증 결과 (E2E 테스트)

[tests/test_e2e_ingest.py](file:///Users/donghakim/ml_quant/tests/test_e2e_ingest.py) 및 `quant features` 실행 결과:

```bash
Initializing DBs... (quant init-db)
Registering Symbol AAPL... (SymbolRepo -> MarketDataService)
Running Ingest... (AAPL 수집 중)
  - Ingested 6591 rows for AAPL
Verifying DuckDB ohlcv rows...
Count in ohlcv: 6591
✅ E2E Verification Success!
```

---

## 3. 특징량 및 레이블 파이프라인 구축 완료

### 퀀트 지표 및 레이블 목록
- **Features**: Momentum, Volatility, Trend, Volume 등 12개 핵심 기술적 지표
- **Labels**: `fwd_ret_60d` (미래 수익률), `direction_60d` (상승/하락 여부)

### 시계열 분할 (ML Splits) 검증
`splits.py`를 통해 학습/검증 세트 사이의 **Purge Gap(60d)**을 설정하여 미래 데이터가 학습에 누수되지 않음을 확인했습니다.

```bash
# 시계열 분할 검증 예시
Split 1:
  Train: 2013-01-05 ~ 2014-05-19 (500 days)
  Test:  2014-08-28 ~ 2014-12-05 (100 days)
  [Pass] No Overlap | [Pass] Gap between train and test: 100 days
```

### CLI 실행 및 저장 결과
```bash
# 레이블 생성 실행
$ quant labels --horizon 60
[16:15:16] INFO Computing labels for AAPL (horizon=60, version=v1)...
[16:15:16] INFO Successfully saved labels for AAPL.

# DuckDB 저장 결과 확인
$ SELECT symbol, count(*) FROM labels GROUP BY symbol;
AAPL | 6591
NVDA | 6591
...
```

---

## 4. 대시보드 업데이트
Streamlit 대시보드([app/streamlit_app.py](file:///Users/donghakim/ml_quant/app/streamlit_app.py))에 **Labeled Data Monitor** 섹션을 추가하여 특징량과 레이블이 조화롭게 준비되었는지 확인할 수 있게 개선했습니다.

---

## 5. 최종 구성도
```mermaid
graph TD
    CLI[quant CLI] --> Service[MarketDataService]
    Repo[SymbolRepo] --> Service
    Service --> Client[market_data Client]
    Service --> Store[quant DB Stores]
    Client --> API((Alpha Vantage))
    Store --> DuckDB[(DuckDB)]
    Store --> SQLite[(SQLite)]
```

이제 `market_data`는 순수하게 데이터만 가져오고, 모든 관리와 정책은 `src/quant` 내에서 이루어집니다. 추가 요청 사항이 있으시면 말씀해 주세요!

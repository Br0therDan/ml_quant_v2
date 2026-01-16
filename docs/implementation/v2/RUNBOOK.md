# RUNBOOK.md (V2)
- Version: v2.0.0
- Created: 2026-01-15
- Last Updated: 2026-01-15

> 본 문서는 V2 시스템을 **반복/재현 가능하게 실행**하기 위한 절차를 정리한다.  
> 시스템 계약은 `docs/V2_SYSTEM_SPEC.md`를 따른다.

---

## 0. 전제
- DB 위치:
  - DuckDB: `./data/quant.duckdb`
  - SQLite: `./data/meta.db`
- Alpha Vantage API Key는 `.env`에 설정되어 있어야 한다.
- **운영 규칙: 배치 실행(ingest/features/labels/recommend/backtest) 수행 시 Streamlit은 종료한 상태에서 실행한다.**

---

## 1. 초기화

### 1.1 환경 구성
```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

### 1.2 DB 초기화
```bash
quant init-db
```

---

## 2. 심볼 등록 (Meta DB)

> 심볼 등록 명령이 구현되어 있다면 사용한다.  
> 미구현 시에는 SQLite GUI 도구로 `symbols`에 직접 추가해도 된다.

예시(추후 커맨드):
```bash
quant symbols add AAPL
quant symbols add MSFT
quant symbols list
```

---

## 3. 데이터 적재 (Ingestion)

### 3.1 특정 심볼 적재
```bash
quant ingest --symbols AAPL MSFT
```

### 3.2 적재 확인 (DuckDB)
DuckDB GUI 또는 쿼리로 확인:
```sql
SELECT symbol, max(ts) AS last_ts, count(*) AS rows
FROM ohlcv
GROUP BY symbol
ORDER BY last_ts DESC;
```

---

## 4. 피처/레이블 생성

### 4.1 피처 생성
```bash
quant features --feature-version v1
```

### 4.2 레이블 생성
```bash
quant labels --label-version v1 --horizon 60
```

---

## 5. 모델 학습/스코어링 (선택)
모델 기반 신호를 사용할 경우:
```bash
quant train --task bull
quant train --task bear
quant score --asof 2025-12-31
```

---

## 6. 추천 생성 (Targets)
```bash
quant recommend --strategy strategies/example.yaml --asof 2025-12-31
```

확인:
```sql
SELECT *
FROM targets
WHERE study_date = DATE '2025-12-31'
ORDER BY approved DESC, score DESC
LIMIT 50;
```

---

## 7. 백테스트 실행
```bash
quant backtest --strategy strategies/example.yaml --from 2024-01-01 --to 2025-12-31
```

확인:
```sql
SELECT *
FROM backtest_summary
ORDER BY created_at DESC
LIMIT 20;
```

---

## 8. Streamlit 실행
```bash
streamlit run app/streamlit_app.py
```

### 8.1 확인 포인트
- Data Monitor: 심볼별 last_ts 표시
- Predictions/Targets: 최신 추천/점수 표시
- Backtest Summary: run별 성과 비교
- Trading 탭: 플레이스홀더(실행 비활성)

---

---

## 10. Phase P1 검증 절차 (Meta DB & Run Registry)

### 10.1 DB 초기화 검증
```bash
quant init-db
```
- DuckDB와 SQLite 파일이 `./data/` 아래 생성되는지 확인한다.
- 출력된 `Run ID`가 SQLite의 `runs` 테이블에 `init-db` 종류로 기록되었는지 확인한다.

### 10.2 Run Registry 동작 확인
```bash
quant config
```
- 실행 후 `Run ID`가 생성되는지 확인한다.
- SQLite에서 다음 쿼리로 실행 이력을 확인한다:
  ```sql
  SELECT * FROM runs ORDER BY started_at DESC LIMIT 5;
  ```

### 10.3 DB 스키마 검증
**SQLite (Meta):**
```sql
SELECT name FROM sqlite_master WHERE type='table';
-- 출력: symbols, experiments, models, runs 등 4개 이상
```

**DuckDB (Fact):**
```sql
-- targets 테이블 존재 확인
DESCRIBE targets;
```

---

## 11. 장애/복구
- `runs` 테이블에서 실패한 run의 `error_text` 확인
- DuckDB/SQLite 파일이 깨졌다면 초기 단계에서는 재생성(drop/recreate) 허용

## 운영 및 유지보수

### 데이터베이스 마이그레이션 (Phase P5 보완)
v2.0.0에서 백테스트 상세 통계 지표 저장을 위해 `backtest_summary` 테이블 스키마가 변경되었습니다. 기존 DB 사용자는 아래 쿼리들을 차례로 실행하십시오.

```sql
-- DuckDB CLI 또는 Python 환경에서 실행
ALTER TABLE backtest_summary ADD COLUMN mean_daily_return DOUBLE;
ALTER TABLE backtest_summary ADD COLUMN std_daily_return DOUBLE;
ALTER TABLE backtest_summary ADD COLUMN annual_factor DOUBLE;
ALTER TABLE backtest_summary ADD COLUMN n_days BIGINT;
```

> [!IMPORTANT]
> 마이그레이션 도중 DuckDB 파일 락이 발생하지 않도록 Streamlit 앱을 종료하고 수행하십시오.

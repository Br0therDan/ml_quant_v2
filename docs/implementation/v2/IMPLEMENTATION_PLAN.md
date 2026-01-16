# IMPLEMENTATION_PLAN.md (V2)
- Version: v2.0.0
- Created: 2026-01-15
- Last Updated: 2026-01-15

> 본 문서는 **V2_SYSTEM_SPEC.md** 및 **DB_SCHEMA.md**를 기준으로 작성된 실행 계획이다.  
> 모든 구현은 **계약(Contracts)** 을 준수해야 하며, 작업 완료 기준은 **Done Criteria**로 판정한다.

---

## 1. Executive Summary
V2는 “프로덕션 체인”을 팀/역할 단위가 아닌 **모듈 경계 + 데이터 계약**으로 구현한다.  
실거래(Paper/Live Trading)는 V3에서만 수행하며, V2에서는 **실험/추천/백테스트** 루프를 안정적으로 구축한다.

핵심 성공 조건은 다음 3가지다.
1) 데이터/피처/추천/백테스트 결과가 **DB 계약에 따라 저장**될 것  
2) 모든 실행은 `run_id`로 추적 가능할 것  
3) Streamlit은 **실험 트리거 + 결과 비교 UI**로 작동할 것 (거래 실행 금지)

---

## 2. Objective
- Alpha Vantage 기반 데이터 수집 파이프라인을 구축하고 DuckDB에 SSOT로 저장한다.
- Feature/Label store를 버저닝 기반으로 운영 가능하게 만든다.
- YAML 전략 정의(조립 전용)로 추천 및 감독(Supervisor) 단계를 표준화한다.
- Daily close + 비용 파라미터 기반의 백테스트 엔진을 제공한다.
- Streamlit에서 전략 선택/실행/비교를 인터랙티브하게 지원한다.

---

## 3. Progress Dashboard

| Phase | Scope | Status |
|---|---|---|
| P0 | Repo & Docs Baseline | [ ] |
| P1 | Meta DB(SQLModel) & Run Registry | [ ] |
| P2 | Data Curator (Ingest) | [ ] |
| P3 | Feature Store (Features/Labels) | [ ] |
| P4 | Strategy Lab + Supervisor + Targets | [ ] |
| P5 | Backtest Engine v1 | [ ] |
| P6 | Streamlit Interactive Lab | [x] |
| P7 | Batch Orchestrator (Pipeline Runner) | [x] |

---

## 4. Implementation Plan

> 규칙:
> - 모든 작업 항목은 체크박스를 포함한다.
> - 각 Phase 끝에는 산출물(Artifacts)과 Done Criteria를 명시한다.
> - 일정(주차/일차) 표기는 포함하지 않는다.

---

### Phase P0 — Repo & Docs Baseline

#### Tasks
- [ ] `docs/` 디렉토리 구성 및 문서 배치
- [ ] `V2_SYSTEM_SPEC.md`, `DB_SCHEMA.md`를 docs로 이동/링크 정리
- [ ] 프로젝트 구조를 SSOT 기준으로 모듈 디렉토리 생성
  - [ ] `src/quant/data_curator`
  - [ ] `src/quant/feature_store`
  - [ ] `src/quant/strategy_lab`
  - [ ] `src/quant/portfolio_supervisor`
  - [ ] `src/quant/backtest_engine`
  - [ ] `src/quant/batch_orchestrator`
- [ ] 기본 로그 정책(파일/콘솔) 합의 및 적용

#### Expected Artifacts
- `docs/V2_SYSTEM_SPEC.md`
- `docs/DB_SCHEMA.md`
- `docs/IMPLEMENTATION_PLAN.md`
- 모듈 디렉토리 트리

#### Done Criteria
- `rg "data_curator|feature_store|strategy_lab" -n src/quant` 결과가 모듈 구조를 반영한다.

---

### Phase P1 — Meta DB(SQLModel) & Run Registry

#### Tasks
- [ ] SQLite Meta DB를 SQLModel 기반으로 구성
  - [ ] `symbols`, `experiments`, `models`, `runs` SQLModel 정의
- [ ] DB engine/session 유틸리티 제공 (`get_session()`)
- [ ] Run Registry 규칙 구현
  - [ ] `run_start(kind, config_json)` → `run_id` 생성
  - [ ] `run_success(run_id)` / `run_fail(run_id, error_text)` 기록
- [ ] CLI `init-db`가 DuckDB+SQLite를 모두 초기화하도록 정리
  - [ ] DuckDB: schema SQL 적용
  - [ ] SQLite: SQLModel `create_all()`

#### Expected Artifacts
- `src/quant/models/*.py`
- `src/quant/db/engine.py`
- `src/quant/repos/run_registry.py` (또는 유사 모듈)
- `quant init-db` 동작 보장

#### Done Criteria
- `quant init-db` 실행이 성공한다.
- SQLite에서 `runs` 테이블이 생성된다.
- 샘플 run 기록이 생성되고 조회 가능하다. (예: `quant config` 실행 후 run 기록)

---

### Phase P2 — Data Curator (Ingest)

#### Tasks
- [ ] Alpha Vantage Provider 구현(HTTP 호출 레이어 분리)
  - [ ] retry/backoff
  - [ ] 응답 유효성 검사
- [ ] DuckDB `ohlcv` upsert 저장 구현
- [ ] 최신성 판단(증분 업데이트)
  - [ ] 심볼별 `max(ts)` 기준 이후만 삽입
- [ ] 품질 게이트(Quality Gate) 최소 구현
  - [ ] 중복/누락 탐지(기본)
  - [ ] OHLCV 필드 유효성 검사
- [ ] CLI `quant ingest` 구현
  - [ ] `--symbols` 또는 활성 심볼 목록 기반 실행

#### Expected Artifacts
- `src/quant/data_curator/ingest.py`
- DuckDB `ohlcv` 데이터 누적
- `quant ingest` 커맨드

#### Done Criteria
- `quant ingest --symbols AAPL MSFT` 실행 성공
- DuckDB에서 `ohlcv` row 수가 증가한다.
- Streamlit Data Monitor에서 마지막 ts가 표시된다.

---

### Phase P3 — Feature Store (Features/Labels)

#### Tasks
- [ ] `features_daily` 생성(최소 피처 세트)
  - [ ] momentum/volatility/gap/volume ratio 등
  - [ ] `feature_version` 필수
- [ ] `labels` 생성
  - [ ] `fwd_ret_60d` 또는 `direction_60d`
  - [ ] `label_version` 필수
- [ ] NaN/Inf 비율 검사 및 저장 전 게이트 구현
- [ ] CLI `quant features`, `quant labels` 구현

#### Expected Artifacts
- DuckDB `features_daily` / `labels`
- feature_version/label_version 운용 규칙

#### Done Criteria
- `quant features --feature-version v1`
- `quant labels --label-version v1 --horizon 60`
- DuckDB에서 해당 버전의 feature/label이 조회된다.

---

### Phase P4 — Strategy Lab + Supervisor + Targets

#### Tasks
- [ ] YAML 전략 파일 로딩(조립 전용)
  - [ ] 최소 스키마 검증
  - [ ] `strategy_id/version` 강제
- [ ] 추천 생성(`targets`)
  - [ ] Top-K 선정 + weight 계산(sizing)
- [ ] Supervisor Lightweight 5룰 적용
  - [ ] R1~R5
  - [ ] 승인 결과(`approved`) 및 `risk_flags` 기록
- [ ] CLI `quant recommend` 구현
  - [ ] `--strategy path/to/strategy.yaml`
  - [ ] `--asof YYYY-MM-DD`

#### Expected Artifacts
- `strategies/*.yaml`
- DuckDB `targets` populated
- Supervisor 승인/플래그 출력

#### Done Criteria
- `quant recommend --strategy strategies/example.yaml --asof 2025-12-31`
- DuckDB `targets`에 `approved`가 채워진 레코드가 생성된다.

---

### Phase P5 — Backtest Engine v1

#### Tasks
- [ ] Backtest 엔진 구현(정책 기반)
  - [ ] 체결가정: daily close
  - [ ] fee/slippage bps 파라미터 적용
- [ ] 거래 로그 `backtest_trades` 생성
- [ ] 요약 `backtest_summary` 생성
- [ ] CLI `quant backtest` 구현
  - [ ] 전략 YAML 기반 실행
  - [ ] 기간(from/to) 지정

#### Expected Artifacts
- DuckDB `backtest_trades`, `backtest_summary`
- Backtest 리포트 기본 뷰(표)

#### Done Criteria
- `quant backtest --strategy strategies/example.yaml --from 2024-01-01 --to 2025-12-31`
- `backtest_summary`에 run_id 단위 레코드가 저장된다.

---

### Phase P6 — Streamlit Interactive Lab

#### Tasks
- [x] Streamlit에서 전략 YAML 선택 UI 제공
- [x] ingest/features/labels/recommend/backtest 실행 트리거 제공(실험 목적)
- [x] 실행 결과 비교(Backtest summary 비교)
- [x] Trading(주문 실행) 탭은 플레이스홀더로 유지
  - [x] “V3에서 활성화” 명시
  - [x] 버튼 비활성 또는 더미

#### Expected Artifacts
- Streamlit 페이지 확장
- 전략별 결과 비교 UI

#### Done Criteria
- Streamlit에서 전략을 선택하고 backtest를 실행할 수 있다.
- 결과가 DB에 저장되고 UI에서 조회된다.
- Trading 탭은 기능을 수행하지 않는다.

---

### Phase P7 — Batch Orchestrator (Pipeline Runner)

#### Tasks
- [ ] 스테이지 순차 실행 파이프라인 정의
  - [ ] ingest → features → labels → recommend → backtest
- [ ] `quant pipeline run` 구현
  - [ ] 실패 시 중단 + runs에 기록
- [ ] 최소한의 재시도 정책(선택)

#### Expected Artifacts
- `src/quant/batch_orchestrator/pipeline.py`
- end-to-end 실행 1커맨드 지원

#### Done Criteria
- `quant pipeline run --strategy strategies/example.yaml --from ... --to ...`
- 단일 커맨드로 E2E 수행 및 runs 기록이 남는다.

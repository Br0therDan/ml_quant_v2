# V2_SYSTEM_SPEC.md (SSOT)
- Version: v2.0.0
- Created: 2026-01-15
- Last Updated: 2026-01-15

> 이 문서는 **V2 전환/구축의 SSOT(Single Source of Truth)** 이다.  
> 구현/리팩토링/확장 판단은 항상 본 문서의 계약(Contracts)을 최우선 기준으로 한다.

---

## Document Index
아래 문서는 V2 구축을 위한 **공식 문서 세트**이며, 각 문서는 서로 다른 책임을 가진다.

| Document | Role | When to Use |
|---|---|---|
| `V2_SYSTEM_SPEC.md` | **SSOT / 계약서(헌법)** | 경계/규칙/스키마/가정이 흔들릴 때 최우선 참조 |
| `DB_SCHEMA.md` | **DB 계약(테이블/필드) 상세** | DuckDB/SQLite/YAML 스키마를 구현/검증할 때 |
| `IMPLEMENTATION_PLAN.md` | **실행 계획(Phase/Checklist)** | Copilot 작업 지시, 스프린트 단위 진행 관리 |
| `RUNBOOK.md` | **운영/실험 실행 레시피** | 반복 실행(ingest→feature→recommend→backtest) 절차 확인 |
| `YAML_SCHEMA.md` | **전략 YAML 스키마 규약** | YAML을 조립 설정으로 유지하고 확장 오남용 방지 |

> 원칙: 구현/리팩토링 시 충돌이 발생하면 **V2_SYSTEM_SPEC.md → DB_SCHEMA.md** 순으로 판단한다.

---

## 0. Executive Summary
V2는 **CLI/TUI + Streamlit 기반의 인터랙티브 실험 환경**으로 확장한다.  
단, **Paper/Live Trading 실행은 V3에서 구현**하며 V2에서는 **플레이스홀더(비활성 UI)로만 제공**한다.

V2의 핵심 목표는 다음이다.
- “팀 기반 프로덕션 체인”을 **모듈 경계/계약(Contract)** 으로 재현
- 데이터 → 피처 → 전략 → 백테스트 → 배치/감독까지 **재현 가능한 실험 루프** 구축
- YAML은 **전략 조립용 설정 파일**로만 사용 (DSL 확장 금지)

---

## 1. Goal / Non-Goal

### 1.1 Goals
- 데이터 수집(Alpha Vantage) → 저장(DuckDB) → 검증(Quality Gate) 자동화
- 피처/레이블 버저닝 기반의 실험 파이프라인 구축
- 전략 정의(Strategy SSOT)를 YAML로 관리
- Backtest(일관된 체결 가정)로 성과 평가 및 결과 저장
- Portfolio Supervisor(경량 규제 5종)로 리스크 제어
- Streamlit에서 **전략 선택/실험 트리거/결과 비교**까지 인터랙티브 지원

### 1.2 Non-Goals (V2에서 하지 않음)
- 실거래/주문 실행 (Paper/Live Trading)  
  - V2에서는 UI/모듈 “자리만” 마련하고, 실행은 금지
- 초단타/실시간 체결 최적화
- 엔터프라이즈 SaaS(멀티유저, 클라우드 운영, IAM/RBAC 등)

---

## 2. Architecture Overview (Modules = Teams)

V2는 아래 “6팀 프로덕션 체인”을 **6개 모듈**로 구현한다.

| Team (Book) | Module (Code) | Core Responsibility | Outputs (Contracts) |
|---|---|---|---|
| 데이터 큐레이터 | `data_curator` | 수집/정합성/스냅샷 | DuckDB `ohlcv` |
| 특성 분석 | `feature_store` | 피처/레이블 생성/버저닝 | DuckDB `features_daily`, `labels` |
| 전략 | `strategy_lab` | YAML 기반 조립/랭킹/추천 | DuckDB `targets`(또는 결과 파일) |
| 백테스터 | `backtest_engine` | 정책 실행/성과 측정 | DuckDB `backtest_trades`, `backtest_summary` |
| 배치 | `batch_orchestrator` | 실행 순서/상태 관리 | SQLite `runs` |
| 포트폴리오 감독 | `portfolio_supervisor` | 규제/제약/승인 | 승인된 `targets` + `risk_flags` |

> **원칙:** 각 모듈은 “입력/출력 계약”으로만 연결되며, 내부 구현을 공유하지 않는다.

---

## 3. Data Contracts (SSOT)

### 3.1 Datastores
- **DuckDB**: 시계열 사실 데이터 + 실험 산출물 저장 (대용량/분석 최적)
- **SQLite (SQLModel/SQLAlchemy)**: 메타데이터 + 실행 상태 관리

### 3.2 DuckDB Fact Tables (필수)
- `ohlcv`: 가격/거래량 원천(SSOT)
- `returns`: 수익률 파생(옵션)
- `features_daily`: long-form 피처 저장(버전 포함)
- `labels`: long-form 레이블 저장(버전 포함)
- `predictions`: 모델 예측 저장(버전/모델ID 포함)
- `targets`: 전략 추천 포지션(승인 전/후 포함)
- `backtest_trades`, `backtest_summary`: 백테스트 로그/요약

### 3.3 SQLite Meta Tables (필수)
- `symbols`: 유니버스 관리
- `experiments`: 실험 정의(피처/레이블/전략 연결)
- `models`: 모델 레지스트리
- `runs`: 배치/실행 로그 및 에러 기록

---

## 4. Strategy SSOT = YAML (Configuration Only)

### 4.1 YAML 원칙
- YAML은 **전략 조립(Assembly) 설정 파일**이다.
- YAML은 “연산/로직”을 담지 않는다. (DSL 확장 금지)
- YAML은 반드시 `strategy_id`를 갖는다.
- V2는 **코드 기반 구현(파이썬 모듈)** + YAML 조립 방식으로 운영한다.

### 4.2 Minimal YAML Schema (V2)
필수 필드(최소):
- `strategy_id`
- `version`
- `universe`
- `signal`
- `rebalance`
- `portfolio`
- `supervisor`
- `execution`
- `backtest`

> 구체 필드 정의는 `DB_SCHEMA.md` 내 “Strategy YAML Schema” 섹션을 따른다.

---

## 5. Backtest Assumptions (Contract)

### 5.1 Execution Model
- 체결 가격: **Daily Close**
- 체결 시점: 리밸런싱 시점의 close에서 체결된 것으로 가정
- 수수료/슬리피지:
  - `fee_bps`
  - `slippage_bps`
  - YAML에서 조정 가능

### 5.2 Output Contract
- 모든 백테스트 실행은 다음 산출물을 생성해야 한다.
  - DuckDB: `backtest_trades`
  - DuckDB: `backtest_summary`

---

## 6. Portfolio Supervisor (Lightweight Rules, V2)

V2에서는 복잡성 폭발을 피하기 위해 **5개 규칙만 강제**한다.

| Rule ID | Name | Default Intent |
|---|---|---|
| R1 | Gross Exposure Cap | 총 투자 비중 상한 |
| R2 | Max Position Weight | 종목당 최대 비중 상한 |
| R3 | Max Positions | 동시 보유 종목 수 제한 |
| R4 | Turnover Cap | 리밸런싱 교체량 제한 |
| R5 | Score Floor / Top-K Gate | 애매한 후보 제거 |

Supervisor는 “전략이 만든 targets”를 입력으로 받아:
- 승인된 targets (`approved=true`)
- 위험 플래그 (`risk_flags`)
를 출력한다.

---

## 7. CLI Contracts (V2)

### 7.1 필수 명령 (최소)
- `quant init-db`
- `quant ingest`
- `quant features`
- `quant labels`
- `quant train`
- `quant score`
- `quant recommend`
- `quant backtest`
- `quant pipeline run` (옵션: 스테이지 순차 실행)

### 7.2 Run Registry Contract (필수)
상태를 바꾸는 모든 CLI 실행은:
- `run_id` 생성
- SQLite `runs`에 기록 (kind/status/started/ended/error)
을 반드시 수행한다.

---

## 8. Versioning & Reproducibility Rules

### 8.1 필수 ID/Version
- `strategy_id` (YAML)
- `feature_version`
- `label_version`
- `model_id`
- `experiment_id`
- `run_id`

### 8.2 재현성 원칙
동일한 입력(데이터 스냅샷 + YAML + 버전 + 파라미터)이면:
- 동일한 산출물(추천/백테스트)이 재현 가능해야 한다.

---

## 9. Quality Gates (필수 검사)

### 9.1 Data Curator Gates
- 중복 제거(upsert)
- 날짜 누락 탐지(영업일 기준은 단계적으로 개선)
- 필드 유효성(open/high/low/close/volume)

### 9.2 Feature/Label Gates
- leakage 없는 split 규칙 준수
- NaN/Inf 비율 제한
- feature_version/label_version 누락 금지

### 9.3 Backtest Gates
- 거래 로그/요약 저장 필수
- 비용(fee/slippage) 적용 여부 기록

---

## 10.Artifacts & Review Protocol

V2는 단일 개발자 환경이더라도 모듈/스프린트 단위 검토가 가능하도록 **Artifact Snapshot**을 남긴다.  
Artifact는 문서 스프롤을 유발하는 “보고서”가 아니라, 최소 단위의 **검토 스냅샷(증거 묶음)** 이다.

### Artifact 생성 규칙 (Required)
- 각 Phase 완료 시점에 아래 경로로 스냅샷을 생성한다.
  - `artifacts/runs/<YYYY-MM-DD>_<phase_name>/SUMMARY.md`
- `SUMMARY.md`는 1페이지 요약으로 제한한다.
- 추가 증거 파일은 선택적으로 첨부할 수 있으나, 폴더당 md 파일은 기본 1개(SUMMARY.md)만 유지한다.

### Artifact 인덱스 규칙 (Required)
- `artifacts/README.md`는 단 하나의 인덱스 파일로 유지한다.
- 인덱스에는 각 스냅샷 폴더 링크와 요약 한 줄만 기록한다.

### SUMMARY.md 최소 포맷 (Required)
`SUMMARY.md`는 아래 항목을 반드시 포함한다.

- Date / Phase / Status (PASS 또는 FAIL)
- What Changed (핵심 변경 3~7줄)
- Artifacts Produced (생성 파일 목록)
- Verification (Done Criteria)  
  - 실행 커맨드
  - DB 검증 쿼리 결과 요약
- Notes / Risks (리스크 1~3개)
- Next (다음 Phase 작업 1~3개)

### 선택 증거 파일 (Optional)
필요 시 아래 파일을 첨부할 수 있다.
- `checks.md` (검증 로그 요약)
- `schema_sqlite.sql` (SQLite schema dump)
- `schema_duckdb.sql` (DuckDB schema dump)
- `tables_preview.csv` (핵심 테이블 샘플 20~100행)
- `diffs.patch` (변경사항 patch)

> 원칙: Artifact는 “검토 가능성”만 보장하고, 상세 보고서를 강제하지 않는다.
---

## 11. Change Log
- v2.0.0 (2026-01-15)
  - Initial SSOT specification for V2

# Quant Lab V2 — Context Handoff (New Chat Thread Starter)

- Owner: **Dan (댄)**
- Assistant: **Harvey (하비)**
- Timezone: Asia/Seoul
- Last updated: **2026-01-16**
- 목적: 이 문서는 **새 채팅방으로 맥락을 안전하게 이전**하기 위한 “1페이지 SSOT 요약”이다.

---

## 1) 프로젝트 한 줄 요약

**Quant Lab V2**는 개인용 금융 퀀트 연구 워크벤치로,  
**Alpha Vantage 데이터 → DuckDB 시계열 저장 → 피처/라벨/추천/백테스트 파이프라인**을 구축하고  
**Streamlit UI를 메인 인터페이스**로 사용한다.

---

## 2) 핵심 목표

### 2.1 제품 관점 (댄의 목표)
- “무엇을 살지 / 언제 / 얼마나 / 어떤 근거로”를 **실험·평가·반복**하는 개인용 퀀트 실험실
- 결과는 Backtest KPI/리포트로 빠르게 검증
- (V3에서) Paper/Live trading은 충분한 실험 이후 구현

### 2.2 시스템 관점
- 데이터/메타 분리:
  - **DuckDB**: OHLCV + features/labels/targets/backtest results (시계열 중심)
  - **SQLite**: runs/experiments/models 등 메타데이터/실행이력 (운영 중심)
- 실행 트래킹: 모든 실행은 SQLite `runs`에 기록
- 전략 설정: **YAML은 전략 조립용 설정 파일로만 제한** (DSL 확장 금지)

---

## 3) 기술 스택

- UI: **Streamlit** (pages 기반 멀티 페이지, sidebar = navigation only)
- DB:
  - **DuckDB** (시계열/분석 질의)
  - **SQLite** (메타데이터, runs)
- Data Provider: **Alpha Vantage (유료 라이선스)**
- ML/FE 라이브러리(후보/설치됨): **scikit-learn, LightGBM** 등
  - 단, V2 단계는 “모델 고도화”보다 “파이프라인/실험 UX” 우선
- 실행: `uv` 기반 환경 (pyproject.toml)

---

## 4) 문서 SSOT 위치

V2 문서들은 아래 경로를 기준으로 관리한다:

- `docs/implementation/v2/V2_SYSTEM_SPEC.md`  (SSOT / 최상위 기준)
- `docs/implementation/v2/DB_SCHEMA.md`       (DuckDB/SQLite/YAML 스키마 계약)
- `docs/implementation/v2/IMPLEMENTATION_PLAN.md` (Phase/Checklist 실행 계획)
- `docs/implementation/v2/RUNBOOK.md`
- `docs/implementation/v2/YAML_SCHEMA.md`

UI 추가 설계 SSOT:
- `V2_UI_SYSTEM_SPEC.md` (UI IA + 페이지별 목적/입력/버튼/결과 계약)

---

## 5) Phase 진행 현황 (요약)

> V2는 Phase 기반으로 점진 구축되었으며, 현재 **P7 완료 + UAT 진행 예정**.

- P1: Meta DB / runs registry ✅
- P2: Data Curator / Ingest ✅  
  - AV provider + retry/backoff  
  - DuckDB OHLCV 증분 적재 (upsert)  
  - Quality Gate 적용  
  - runs 기록
- P3: Feature Store ✅
- P4: Recommend/Targets ✅ (기본 형태)
- P5: Backtest Engine ✅ (+ refinement 포함)
- P6: Streamlit UI (Dashboard/Explorer/Analyzer) ✅ (초기 형태)
- P7: Batch Orchestrator ✅  
  - `quant pipeline run` 형태로 ingest→features→labels→recommend→backtest 지원  
  - `--stages`, `--dry-run`, fail-fast, runs 기록

---

## 6) 현재 UI 상태 (핵심 관찰)

### 6.1 이미 구현된 UI (현재)
- Dashboard (통합 요약)
- Market Explorer (데이터 탐색)
- Targets Analyzer (초기/미흡)
- Backtest Analyzer (초기/미흡)

### 6.2 현재 문제점 / 보완 포인트
- UI가 **Read-only에 가까움**  
  → CLI 기능(실행)을 GUI로 끌어올려야 진짜 Workbench가 됨
- Pipeline Status 페이지는 인사이트가 약함  
  → Dashboard 흡수 또는 Debug 페이지로 격리 권장
- Backtest에서 트레이드 마커 UX 미흡  
  - “테스트 기간 종가 라인 차트 위에 buy/sell 마커”가 의미가 큼  
  - chart mode 토글 동작/오버레이 구조 수정 필요
- Targets Analyzer는 목적이 불명확  
  - 추천 스냅샷 + 전일 대비 변화(delta) 중심으로 재정의 권장

---

## 7) 권장 UI IA (CLI 기능을 GUI로 흡수하기 위한 추가 페이지)

V2에서 “CLI를 거의 쓰지 않아도 되는 수준”을 목표로 아래 최소 6페이지 구성을 제안:

1) **Dashboard** (통합 상태 + Quick Actions)
2) **Run Center (NEW)**: 오케스트레이션/실행기 + 로그
3) **Data Center**: 심볼/인게스트/품질/차트
4) **Feature Lab (NEW)**: 피처 엔지니어링/분석 (분포/상관/결측)
5) **Strategy Lab (NEW)**: YAML 검증/요약/평가 실행
6) **Backtest Lab**: 실행 + KPI + 트레이드 마커 분석

(선택 확장)
- Targets & Supervisor
- Runs & Artifacts Explorer

---

## 8) UI/UX 기본 원칙 (댄의 선호)

- Sidebar는 **앱 네비게이션 전용**
- 페이지 내부는 **좌 Controls / 우 Results** 2-panel 고정
- **전체 화면 스크롤을 싫어함**  
  - Tabs / Expander / 컨테이너 내부 스크롤을 선호
- 커스텀 CSS 덕지덕지는 피함 (최소화)
- 패널 컨테이너는 border 정렬(상/하단)되게 구성

---

## 9) “UI에서 실행” 방향성 (중요 결정)

댄의 우선순위: **현재는 UI가 더 중요**  
CLI는 데이터/협업/자동화 용도로 유지, 배치 자동화는 나중에.

따라서 V2에서는 다음 방식을 채택한다:

- UI 버튼 → **CLI subprocess 실행** (즉시 적용 가능)
- 실행 중 → **로그 다이얼로그/패널**로 출력 표시
- 로그는 표준 경로에 저장:
  - `artifacts/runs/<run_id>/pipeline.log`
- 실행 단일화(동시 실행 제한)로 DuckDB lock 위험을 낮춘다.

---

## 10) Strategy Lab 편집기 (Monaco) 계획

- Streamlit 내 YAML 편집을 위해 **Monaco Editor 사용**
- 기본 저장 정책: **Save As 중심**
  - 저장 위치: `./strategies/generated/`
- Validate 통과 시에만 실행/저장 허용 (gate)

---

## 11) UAT (User Acceptance Test) 체크리스트

### 11.1 기능 UAT (필수)
- [ ] UI에서 ingest 실행 가능 (run_id + log + runs 기록)
- [ ] UI에서 features/labels/recommend/backtest 실행 가능
- [ ] Dashboard에서 최근 runs/상태가 갱신됨
- [ ] Backtest KPI가 정상 계산/표기 (NaN 노출 금지)
- [ ] Trade marker가 close line 위에 의미 있게 표시됨

### 11.2 데이터 UAT (필수)
- [ ] OHLCV 커버리지 (누락/중복/invalid price 없음)
- [ ] 증분 적재가 정상 동작(중복 적재 없이 upsert)
- [ ] Quality Gate가 기대대로 필터링

### 11.3 UX UAT (권장)
- [ ] sidebar navigation-only 유지
- [ ] page-level scroll 최소화
- [ ] long tables are in expanders / internal scroll

---

## 12) 다음 액션 (새 채팅방에서 할 일)

1) **Run Center UI 구현** (오케스트레이션 + 로그)
2) **Feature Lab UI 구현**
3) **Strategy Lab + Monaco Editor + Save As + Validate**
4) Backtest trade marker 및 chart toggle 정상화
5) Targets Analyzer를 “delta 중심”으로 재정의

---

## 13) 참고: 대화 스타일 / 운영 원칙

- 대화는 한국어(반말)
- 하비는 “냉정한 전문가 + 강한 주장/반박 가능”
- 목표는 **실험 속도(생산성)와 일반화 성능(과최적화 회피)**를 동시에 확보하는 것

---

### 부록 A) (옵션) CLI 핵심 명령 템플릿

> 실제 커맨드명은 repo 구현에 맞춰 조정.

- 단일 파이프라인:
  - `uv run quant pipeline run --strategy <yaml> --from <YYYY-MM-DD> --to <YYYY-MM-DD> --symbols AAPL`
- 스테이지 선택:
  - `uv run quant pipeline run --strategy <yaml> --stages ingest,features --from ... --to ...`
- 드라이런:
  - `uv run quant pipeline run --strategy <yaml> --dry-run --from ... --to ...`

# [V2] Streamlit GUI Implementation Plan (Run Center + Artifacts SSOT)

- 버전: v0.1
- 작성일: 2026-01-16
- 최종수정일: 2026-01-16

## 1. Executive Summary

이 계획서는 Quant Lab V2 Streamlit UI를 **Run Contract(artifacts SSOT + run_id UUID + run_slug alias)** 위에서 “운영 친화적 관측 콘솔”로 재정렬하기 위한 구현 단계안을 제시합니다. 핵심은 Run Center가 Plan(dry-run)과 Run(execute)을 **서로 다른 정체성**으로 다루되(Plan: `plan_*`, Run: UUID), 사용자가 UI에서 **run_id 기준으로 실행 상태를 안정적으로 재구성**하도록 하는 것입니다.

본 계획은 “대규모 리팩토링”을 피하고, 기존 페이지 책임(Production Chain Role IA)을 유지하면서 Run Center/데이터 액세스/검증 레이어를 최소 변경으로 안정화하는 것을 목표로 합니다.

## 2. Objective

### 2.1 Scope

- Run Center
  - Plan View: `PLAN_JSON`/`plan.json` 기반 계획 표시(요청 vs resolved)
  - Run View: `run.json`/`pipeline.log`/`stages/*/result.json` 기반 실행 관측
  - History: alias index(`artifacts/index/runs/*.json`) + artifacts 기반 상세 조회
- Cross-page
  - 다른 페이지는 실행 금지 유지
  - run_id 기반 deep link(분석/디버깅 동선 단축)

### 2.2 Non‑Goals

- 파이프라인 stage 추가/변경
- Streamlit에서 DB write, 외부 API 호출
- ML/추천 알고리즘 변경(POC 외)

### 2.3 Success Criteria (Acceptance)

- Run Center에서 실행한 non-dry-run은 항상 UUID run_id를 가진다.
- Run Center의 실행 로그/상태 파일(`pipeline.log`, `pipeline.pid`, `exit_code.txt`)이 항상 `artifacts/runs/<run_id>/` 아래에 존재한다.
- UI는 `pipeline.log`의 `PROGRESS_JSON:` 이벤트를 표시할 수 있다(없으면 graceful fallback).
- `run.json`/`result.json` 스키마가 일부 달라도 UI가 깨지지 않는다(tolerant parsing).

## 3. Progress Dashboard

| Milestone             | Outcome                      | Status |
| --------------------- | ---------------------------- | ------ |
| M0 Contract Alignment | Plan↔Run 경로/정체성 정합    | ⏳      |
| M1 Observability      | Run View(로그/진행/요약)     | ⏳      |
| M2 History/Lookup     | alias index 기반 검색/리스트 | ⏳      |
| M3 Deep Links         | 페이지간 run_id 내비게이션   | ⏳      |
| M4 Hygiene            | SQL/validator/메시지 정합    | ⏳      |

## 4. Implementation Plan (Checklist)

### M0 — Contract Alignment (1~2일)

- [ ] Run Center에서 Run(execute) 클릭 시 **UUID run_id를 생성**
  - 현재: Plan의 `run_id=plan_*`를 재사용하는 흐름이 존재(계약과 충돌 가능)
  - 목표: Plan은 plan_id로 보존, Run은 uuid로 실행
- [ ] Run 실행 시 `artifacts_dir = artifacts/runs/<uuid>/`로 고정
  - ExecutionManager wrapper가 기록하는 `pipeline.log/pipeline.pid/exit_code.txt`가 계약 경로에 생성되도록
- [ ] UI session_state에 `{plan_id, run_id(uuid), run_slug(optional)}`를 저장
  - Plan View: plan_id 기반
  - Run View: run_id(uuid) 기반

**Design Note**
- `src/quant/cli.py`는 `--run-id`가 UUID가 아니면 run_slug로 간주하고 UUID를 생성한다.
  - 따라서 UI가 artifacts_dir를 알고 싶다면, 실행 시점에 UUID를 **UI가 직접 생성**해 넘기는 것이 가장 단순.

### M0 상세 설계 (파일/함수 단위)

> 목표: Run Center가 **Plan(`plan_*`)** 과 **Run(UUID)** 을 섞지 않고, 실행 관측(log/pid/exit_code)이 항상 `artifacts/runs/<run_id>/`(UUID)에서 동작하도록 만든다.

#### A) Run Center 상태 모델(세션) 정리

- 현재 문제 요약
  - Plan(dry-run)에서는 `plan.run_id = plan_*` 이고 `plan.artifacts_dir = artifacts/runs/plan_*/` 이다.
  - Run(execute)에서 UI가 `plan.run_id`/`plan.artifacts_dir`를 그대로 쓰면, 실제 pipeline이 UUID로 SSOT를 생성하는 구조와 충돌할 수 있다.
- 제안 상태 모델(최소 변경)
  - `st.session_state["plan"]`: PLAN_JSON 그대로(Plan 전용)
  - `st.session_state["plan_run_id"]`: plan_* (Plan 정체성)
  - `st.session_state["active_run_id"]`: UUID (Run 정체성)
  - `st.session_state["active_run_artifacts_dir"]`: `artifacts/runs/<UUID>/`
  - (옵션) `st.session_state["active_run_slug"]`: `run.json` 로드 후 채움

#### B) Run Center Plan 버튼(현행 유지)

- 파일: `app/pages/2_Run_Center.py`
- 유지하는 것
  - Plan 버튼은 기존처럼 `plan_run_id = plan_...` 를 생성하고 `--dry-run`으로 실행
  - stdout에서 `PLAN_JSON:` 파싱 + `artifacts/runs/<plan_run_id>/plan.json` 생성 검증
- 보강(문서상 요구)
  - Plan View에 “이 plan_id는 실행 run_id(UUID)와 다름”을 명확히 표기

#### C) Run Center Run 버튼(핵심 수정 포인트)

- 파일: `app/pages/2_Run_Center.py`
- 변경 전 위험
  - Run 버튼이 `run_id = plan.get("run_id")` 및 `artifacts_dir = plan.get("artifacts_dir")` 기반으로 실행 관측을 시작
- 변경 후 목표 동작(계약 정합)
  1) `run_uuid = str(uuid.uuid4())`
  2) cmd 생성 시 `--run-id run_uuid`를 전달
  3) `run_artifacts_dir = settings.quant_runs_dir / run_uuid` 로 고정
  4) `ExecutionManager.start_run_with_artifacts(..., artifacts_dir=run_artifacts_dir)` 호출
  5) session_state에 `active_run_id/run_artifacts_dir` 저장

#### D) Run View 데이터 소스 우선순위(관측 안정성)

- 파일: `app/pages/2_Run_Center.py`
- 우선순위(권장)
  1) `active_run_artifacts_dir/pipeline.log` tail
  2) `active_run_artifacts_dir/exit_code.txt` 존재 여부
  3) `active_run_artifacts_dir/run.json` 존재 시 summary 표시
  4) `active_run_artifacts_dir/stages/*/result.json` 존재 시 stage 요약
  5) (fallback) SQLite runs는 “보조 인덱스”로만 사용

#### E) `logs/ui_exec` (SSOT 위반 후보) 처리

- 파일: `app/ui/execution.py`
- 현황
  - 모듈 import 시점에 `logs/ui_exec`를 생성
  - 동시에 `start_run_with_artifacts()`는 artifacts 경로에만 기록하는 방식도 이미 존재
- 목표
  - UI 실행/관측 산출물은 전부 `artifacts/runs/<run_id>/` 아래로 통일
- 권고 변경(최소)
  - `LOG_DIR` 및 관련 함수(`get_log_path`, `start_run`, `run_command_async` 등)를 “레거시”로 간주
  - Run Center에서 사용되는 경로는 `start_run_with_artifacts()` 하나로 고정
  - `LOG_DIR.mkdir(...)` 같은 부작용은 제거하거나 feature-flag로 비활성(예: `QUANT_UI_ENABLE_LEGACY_LOGS=1`일 때만)

#### F) 스키마 내고장성(tolerant parsing) 명세

- 파일: (추후 UI 파서 추가 시) `app/pages/2_Run_Center.py` 또는 `app/ui/run_artifacts.py`(신규 helper가 필요하면)
- `stages/<stage>/result.json`
  - 표준 키: `elapsed_sec`, `errors[]`, `warnings[]`
  - 구버전/변형 키 대비: `duration_sec`, `error_text` fallback 허용
- `run.json`
  - `run_slug/display_name`이 없으면 run_id만 표시

#### G) 수동 UAT 데모 스크립트(M0 합격 기준)

1) Streamlit Run Center에서 Dry Run 실행
   - Plan View에 `plan_*` run_id 표시
   - `artifacts/runs/<plan_*>/plan.json` exists = True
2) Run(Execute) 실행
   - UI가 UUID run_id를 생성해 표시
   - `artifacts/runs/<uuid>/pipeline.pid` 생성
   - `artifacts/runs/<uuid>/pipeline.log` tail이 증가
3) 실패 시나리오(의도적 오류: 잘못된 stage)
   - exit_code.txt 존재 및 non-zero 표시
   - Run View가 깨지지 않고 오류를 표시

### M1 — Run Center Observability (2~3일)

- [ ] Run View에서 `artifacts/runs/<run_id>/pipeline.log` tail을 기본으로 표시
- [ ] `PROGRESS_JSON:` 라인을 파싱해 Progress UI 제공
  - 예: recommend의 날짜별 targets 저장(`event=targets_write`, current/total)
- [ ] `run.json`을 읽어 summary card 구성
  - status, started_at/ended_at, stages_resolved, symbols_resolved, run_slug/display_name
- [ ] `stages/<stage>/result.json` 요약(OK/Fail, elapsed, errors)
  - tolerant: `elapsed_sec` 또는 `duration_sec` fallback

### M2 — Run History / Lookup (2~4일)

- [ ] Run list의 “SSOT 우선순위”를 정의
  1) `artifacts/index/runs/*.json` (slug → run_id)
  2) `artifacts/runs/*/run.json`
  3) SQLite runs(보조 인덱스)
- [ ] 검색 UX
  - run_id(UUID) 직접 입력
  - run_slug로 검색(=alias index resolve)
  - (선택) strategy_id/date range 필터
- [ ] “Run Detail”를 artifacts 기반으로 표시하고, SQLite는 fallback 경고로만 사용

### M3 — Cross‑Page Deep Links (1~2일)

- [ ] Dashboard에서 “최근 run 선택 → Run Center 상세로 이동” 링크
- [ ] Targets Analyzer/Backtest Lab에서 특정 run_id로 필터링(가능한 경우)
- [ ] 모든 페이지에서 실행 유도는 Run Center CTA만 유지

### M4 — Hygiene & UX Consistency (1~2일)

- [ ] `logs/ui_exec` 생성/사용 제거(또는 feature-flag로 비활성)
  - artifacts SSOT 원칙 준수
- [ ] Strategy Lab
  - Save As 메시지에서 `generated/` 표기 제거(실제 저장은 `strategies/`)
  - YAML validator 필수필드 정합(계약 문서/YAML_SCHEMA와 일치)
- [ ] `app/ui/data_access.py`의 f-string SQL을 파라미터 바인딩으로 전환

## Test / Validation Plan

- 최소 pytest 추가(또는 기존 테스트 확장)
  - PLAN_JSON 존재 및 JSON 파싱
  - `artifacts/runs/<plan_id>/plan.json` 생성
  - Run 실행 시 `run_id`가 UUID이며 artifacts 경로에 `pipeline.pid/exit_code.txt` 생성
  - stages subset, invalid stage 입력 시 exit!=0
- 수동 UAT 시나리오(짧게)
  1) Dry Run → validation.ok 확인
  2) Run → Run View에서 log/progress/exit_code 확인
  3) History에서 run_slug 검색 → run_id resolve → 상세 재구성

## Rollout / Rollback

- 롤아웃: M0→M1을 먼저 병합해 계약/관측을 안정화한 뒤 M2/M3를 단계적으로 추가
- 롤백: UI 변경은 Streamlit 레이어에 국한되도록 유지(파이프라인/DB 계약 변경 최소화)

---

### 참고(근거 문서)

- `docs/run_contract.md`
- `docs/ui_philosophy.md`
- `docs/V2_PRODUCTION_CHAIN_ROLES.md`

# [V2] Streamlit GUI Upgrade Report (Evidence-Based)

- 버전: v0.1
- 작성일: 2026-01-16
- 최종수정일: 2026-01-16

## 1. Executive Summary

Quant Lab V2의 Streamlit UI는 큰 틀에서 **Run Center 단일 실행 진입점 / 나머지 페이지 read-only** 원칙을 잘 따르고 있습니다. 다만 “Run Contract(artifacts SSOT + run_id UUID)”를 **UI가 온전히 활용**하기에는 몇 가지 구조적 갭이 남아 있어, 실제 운영(UAT)에서 “실행 진행상태/로그/실패 원인”이 분산되거나(특히 plan artifacts vs run artifacts), 페이지별 관측 데이터가 DB 중심으로 흐르며(artifacts 기반 재구성 부족) 디버깅 속도를 떨어뜨릴 위험이 있습니다.

우선순위(가치/리스크 기준) TOP 5:

1) **Plan(run_id=plan_*) ↔ Run(run_id=UUID) 연결 재설계**: 실행 시 UI가 plan artifacts_dir를 그대로 사용하면서, 실제 pipeline은 UUID run_id로 artifacts를 생성하는 구조가 발생할 수 있음 → Run Center의 log tail / pid / exit_code 파일이 “계약 경로”와 어긋날 위험.
2) **SSOT 위반 후보 제거**: UI 실행 로그용 `logs/ui_exec` 디렉토리 생성은 철학/운영 관점에서 “artifacts 밖 산출물 생성”에 해당.
3) **Artifacts 기반 Run Detail View 확립**: `run.json`/`stages/*/result.json`/`pipeline.log`/`artifacts/index/runs/*.json`를 UI가 1급 시민으로 소비하도록 전환.
4) **데이터 접근 위생 강화**: `app/ui/data_access.py`에 f-string 기반 SQL이 존재(입력값 직접 주입). 로컬 환경이라도 안전/안정성(오류·quote·escape) 측면에서 개선 필요.
5) **Strategy Lab UX/검증 계약 정합성**: Save 메시지/저장 경로, YAML validator의 required fields가 실제 파이프라인/전략 DSL과 불일치할 가능성.

## 2. Objective

### 2.1 목표(Goals)

- Run Center를 “실행 오케스트레이터 + 관측 콘솔”로 승격
  - Plan(dry-run) → Run(execute) 흐름을 **계약 기반(run_id SSOT)** 으로 강제
  - 진행률/상태는 콘솔 텍스트 파싱이 아닌 `pipeline.log`의 `PROGRESS_JSON:` 이벤트로 표시
- 모든 화면이 **artifacts SSOT**를 기준으로 재현/감사 가능하도록 정렬
  - `artifacts/runs/<run_id>/...` + `artifacts/index/runs/<run_slug>.json`

### 2.2 비협상 제약(Non‑Negotiable)

- 실행(서브프로세스 호출)은 Run Center에서만
- UI는 DB write 금지(관리 콘솔로 확장 금지)
- 실행 산출물은 오직 `artifacts/` 아래로만
- stages 확장 금지(V2: ingest/features/labels/recommend/backtest)

### 2.3 Findings (Evidence → Impact → Recommendation)

|   ID | Severity | Finding                                                                     | Evidence (file:line)                                                                                                                                          | Impact                                                                                                                           | Recommendation                                                                                                                                        |
| ---: | -------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| F-01 | Critical | **Run Center가 Plan 결과의 `artifacts_dir`를 그대로 실행 artifacts로 사용** | `app/pages/2_Run_Center.py:185-210` (Run 버튼에서 `run_id=plan.run_id`, `artifacts_dir=plan.artifacts_dir`)                                                   | 실제 pipeline run의 `run_id`가 UUID로 생성될 경우(=계약), UI가 tail 하는 로그/exit_code/pid 경로가 어긋나 실행 관측이 불안정해짐 | Run 버튼은 별도 UUID `run_id`를 생성해 `--run-id <uuid>`로 실행하고, `artifacts_dir=artifacts/runs/<uuid>/`를 사용. Plan dir은 계획 보존용으로만 유지 |
| F-02 | Major    | **UI 모듈 로드시 `logs/ui_exec` 디렉토리를 생성(artifacts 외 산출물)**      | `app/ui/execution.py:15-16`                                                                                                                                   | SSOT 위반 + 운영 시 “산출물 위치 혼선”                                                                                           | UI 실행 로그는 run artifacts(`artifacts/runs/<run_id>/pipeline.log`)로만. `logs/ui_exec`는 제거/비활성화(레거시 경로)                                 |
| F-03 | Major    | **Strategy Lab Save 메시지가 실제 저장 위치와 불일치**                      | `app/pages/5_Strategy_Lab.py:80-86` ("Saved to generated/..."), `src/quant/ui/services/strategy_files.py:40-66` (실제 저장은 `strategies/<basename>`)         | 사용자가 잘못된 SSOT 위치로 오해(특히 `strategies/generated`는 legacy)                                                           | 메시지/UX 문구를 `strategies/`로 정정하고, generated 경로 표기는 제거                                                                                 |
| F-04 | Major    | **YAML validator required fields가 과도/불일치 가능성**                     | `src/quant/ui/services/yaml_validate.py:4-15` (`execution`, `backtest` 강제)                                                                                  | 유효한 전략이 UI에서 INVALID로 표시되어 UAT 마찰 증가                                                                            | V2 최소 요구 필드를 계약 문서(YAML_SCHEMA)와 정렬: "필수" vs "권장"을 분리, 미존재는 warning 처리                                                     |
| F-05 | Major    | **데이터 액세스 레이어에 f-string SQL 존재**                                | `app/ui/data_access.py:69, 118-170, 205+` 등                                                                                                                  | 입력값에 quote/escape가 섞이면 오류·보안 이슈(로컬이라도)                                                                        | 파라미터 바인딩(duckdb `?`, sqlite `?`)로 전환하거나 whitelist 기반 필터링 적용                                                                       |
| F-06 | Medium   | **UI가 artifacts 기반(run.json/result.json/alias index) 소비가 제한적**     | 현행: Run Center는 SQLite/plan 기반 표시가 중심, artifacts index/`run.json`을 직접 읽는 UI 뷰 부족                                                            | “재현 가능한 실행 기록”을 UI에서 즉시 재구성하기 어려움                                                                          | Run Detail View를 artifacts 우선으로 설계(존재 시 artifacts, 없으면 SQLite fallback)                                                                  |
| F-07 | Medium   | **레거시 실행 유틸이 repo에 잔존(혼선 위험)**                               | `src/quant/ui/services/pipeline_runner.py` (현재 코드베이스에서 직접 import 흔적은 희박)                                                                      | Run Center 단일 진입 원칙을 문서/코드 레벨에서 흐릴 수 있음                                                                      | 제거 또는 `legacy/`로 격리 + 문서에 “미사용/금지” 명시                                                                                                |
| F-08 | Medium   | **Stage result 스키마 변형 가능성(구버전 artifacts와 공존)**                | 파이프라인 표준: `elapsed_sec/errors[]` (`src/quant/batch_orchestrator/pipeline.py:681+`), 과거 artifacts에는 `duration_sec/error_text` 형태가 존재할 수 있음 | UI가 run history를 열람할 때 스키마 차이로 깨질 위험                                                                             | UI 파서는 tolerant하게: `elapsed_sec` 우선, 없으면 `duration_sec` fallback 등                                                                         |

## 3. Progress Dashboard

| Area                         |       Current |      Target | Notes                             |
| ---------------------------- | ------------: | ----------: | --------------------------------- |
| Run Center Plan→Run 흐름     |   ⚠️ 부분 정합 | ✅ 계약 정합 | F-01 해결이 최우선                |
| Artifacts SSOT 일원화        |   ⚠️ 부분 위반 |      ✅ 준수 | F-02, F-03                        |
| Run Detail(artifacts 기반)   |        ❌ 미흡 |      ✅ 제공 | run.json/result.json/index 소비   |
| Progress 표시(PROGRESS_JSON) | ⚠️ 로그는 존재 |   ✅ UI 반영 | `pipeline.log` tail + 이벤트 파싱 |
| Query 안전성                 |   ⚠️ 개선 여지 |    ✅ 안정화 | 파라미터 바인딩                   |
| Validator/DSL 정합성         |      ⚠️ 불확실 |      ✅ 정렬 | YAML_SCHEMA/StrategyLoader와 맞춤 |

## 4. Implementation Plan (High-Level)

- [ ] M0: Contract Alignment (Run Center)
  - [ ] Run 실행 시 UUID run_id를 UI가 생성/고정
  - [ ] artifacts_dir를 `artifacts/runs/<uuid>/`로 통일
  - [ ] Plan artifacts(run_id=plan_*)는 별도 보존 + Run과 링크만 유지
- [ ] M1: Run Center Observability
  - [ ] `pipeline.log` tail + `PROGRESS_JSON` 파싱으로 진행률 UI
  - [ ] `run.json`/`result.json` 요약 카드(스키마 tolerant)
- [ ] M2: Run History / Lookup
  - [ ] `artifacts/index/runs/<run_slug>.json` 기반 검색/리스트
  - [ ] SQLite fallback은 “보조 인덱스”로 격하
- [ ] M3: Cross‑Page Deep Links
  - [ ] Dashboard/Analyzer/Backtest에서 run_id 기반 deep link
  - [ ] 사용자는 항상 Run Center로 실행 유도(원칙 유지)

### M0 상세 설계(실행 정합) — 필독

M0는 “UI가 Plan(`plan_*`)과 Run(UUID)을 섞지 않는 것”이 핵심이며, 이 1개만 바로잡아도 Run Center 관측 안정성이 크게 올라갑니다.

- 상세 설계/수용 기준(UAT 스크립트 포함)은 아래 문서의 **"M0 상세 설계 (파일/함수 단위)"** 섹션을 기준으로 구현합니다.
  - `docs/implementation/v2/plan/gui_implementation_plan_v2.md`

---

### 부록: 계약 근거 문서

- `docs/ui_philosophy.md` (Run Center 단일 실행, artifacts SSOT, PROGRESS_JSON)
- `docs/run_contract.md` (run_id UUID vs run_slug alias, stage result 스키마)
- `docs/V2_PRODUCTION_CHAIN_ROLES.md` (생산체인/핸드오버 관점 IA 기준)
